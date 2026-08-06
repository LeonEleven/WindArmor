"""CyberGear 电机驱动统一封装。

支持两种 CAN 通信后端：
  1. usb_can_serial  — USB-CAN 串口 AT 协议转换器
  2. socketcan_hat    — 微雪 2-CH CAN HAT+（通过 python-can 库）

功能：
  - 电机反馈帧解析（位置/速度/力矩/温度/模式/故障）
  - 断线自动重连（指数退避）
  - 反馈数据回调机制（供控制节点做闭环监控）

CyberGear 电机 CAN 帧格式（根据小米官方说明书 v1.2.1）：

  发送帧 — 29-bit 扩展帧：
    CAN ID = (通信类型 << 24) | (主站 ID << 8) | 电机 ID
    Data[0:7] = 8 字节数据（小端序）

  接收反馈帧（通信类型 0x02）：
    CAN ID = (0x02 << 24) | (数据区2 << 8) | 主站 ID
    其中数据区2 (bits 8-23):
      bits  8-15 (CAN bits 8-15): 电机 CAN ID
      bits 16-21 (CAN bits 16-21): 故障信息 (6 位)
      bits 22-23 (CAN bits 22-23): 模式状态
        0 = Reset（复位）
        1 = Cali（标定）
        2 = Motor（运行）

    8 字节数据 (uint16 × 4，小端序):
      Data[0:2] = 位置 [0~65535] → 映射到 [-4π, +4π] rad
      Data[2:4] = 速度 [0~65535] → 映射到 [-30, +30] rad/s
      Data[4:6] = 力矩 [0~65535] → 映射到 [-12, +12] Nm
      Data[6:8] = 温度 (uint16), 值 = 温度°C × 10

通信类型说明：
  0x03 — 进入运控模式
  0x04 — 停止电机
  0x06 — 设置机械零点
  0x12 (18) — 写 SDO（服务数据对象）
  0x02 — 电机状态反馈（接收）
"""

import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

import serial

try:
    import can  # python-can
except Exception:
    can = None


# ---------------------------------------------------------------------------
# 电机反馈数据结构
# ---------------------------------------------------------------------------

@dataclass
class MotorStatus:
    """单台电机的实时反馈状态。

    字段说明：
        motor_id:     电机 CAN ID (1~127)，从反馈帧 CAN ID bits 8-15 提取
        raw_position: 原始位置值（uint16, 0~65535）
        raw_speed:    原始速度值（uint16, 0~65535）
        raw_torque:   原始力矩值（uint16, 0~65535）
        raw_temp:     原始温度值（uint16, temp°C × 10）
        position_rad: 位置（弧度），范围 [-4π, +4π]
        speed_rad_s:  速度（弧度/秒），范围 [-30, +30]
        torque_nm:    力矩（牛·米），范围 [-12, +12]
        temperature:  温度（摄氏度）
        mode:         CAN ID bits 22-23: 0=复位, 1=标定, 2=运行
        fault_flags:  CAN ID bits 16-21: 故障标志位
        timestamp:    接收时间戳（秒，monotonic）
    """
    motor_id: int = 0
    raw_position: int = 0
    raw_speed: int = 0
    raw_torque: int = 0
    raw_temp: int = 0
    position_rad: float = 0.0
    speed_rad_s: float = 0.0
    torque_nm: float = 0.0
    temperature: float = 0.0
    mode: int = 0
    fault_flags: int = 0
    timestamp: float = 0.0

    @property
    def mode_name(self) -> str:
        """运行模式名称。"""
        names = {0: "复位", 1: "标定", 2: "运行"}
        return names.get(self.mode, f"未知({self.mode})")

    @property
    def has_fault(self) -> bool:
        """是否有任何故障。"""
        return self.fault_flags != 0

    @property
    def fault_names(self) -> list:
        """故障名称列表。"""
        bits = {
            0: "欠压",
            1: "过流",
            2: "过温",
            3: "磁编码故障",
            4: "HALL编码故障",
            5: "未标定",
        }
        return [name for bit, name in bits.items() if self.fault_flags & (1 << bit)]


# ---------------------------------------------------------------------------
# 协议常量
# ---------------------------------------------------------------------------

# CyberGear 通信类型
COMM_GET_STATUS = 0x02       # 读取电机状态（接收帧）
COMM_ENABLE = 0x03           # 进入运控模式
COMM_STOP = 0x04             # 停止电机
COMM_SET_ZERO = 0x06         # 设置机械零点
COMM_WRITE_SDO = 18          # 写 SDO 参数（0x12）

# SDO 索引
SDO_RUN_MODE = 0x7005        # 运控模式（1 = 位置模式, 2 = 速度模式, 3 = 电流模式）
SDO_TARGET_POS = 0x7016      # 位置模式角度指令（rad）
SDO_TARGET_SPEED = 0x7017    # 位置模式速度限制（rad/s）

# 反馈帧量程常量（uint16 映射到物理量）
UINT16_MAX = 65535.0
POS_RANGE_MIN = -12.566370614359172   # -4π
POS_RANGE_MAX = 12.566370614359172    # +4π
SPD_RANGE_MIN = -30.0
SPD_RANGE_MAX = 30.0
TORQUE_RANGE_MIN = -12.0
TORQUE_RANGE_MAX = 12.0
TEMP_SCALE = 10.0                     # 温度原始值 / 10 = °C

# USB-CAN 串口 AT 帧格式
AT_PREAMBLE = b"\x41\x54"    # "AT"
AT_TERMINATOR = b"\x0D\x0A"  # "\r\n"

# 重连参数
MAX_RECONNECT_ATTEMPTS = 30
INITIAL_RECONNECT_DELAY = 0.5
MAX_RECONNECT_DELAY = 10.0
RECONNECT_DELAY_MULTIPLIER = 1.5


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _uint16_to_range(raw: int, rmin: float, rmax: float) -> float:
    """将 uint16 原始值线性映射到 [rmin, rmax] 范围。

    参数：
        raw: uint16 原始值（0~65535）。
        rmin: 物理量下限。
        rmax: 物理量上限。

    返回：
        物理量值。
    """
    return rmin + (raw / UINT16_MAX) * (rmax - rmin)


def _parse_feedback_frame(motor_id: int, can_id_29: int, data: bytes) -> Optional[MotorStatus]:
    """解析单帧电机反馈数据（uint16 × 4 + CAN ID 状态位）。

    参数：
        motor_id:   从 CAN ID bits 8-15 提取的电机 ID。
        can_id_29:  完整的 29-bit CAN ID。
        data:       8 字节数据负载。

    返回：
        MotorStatus 对象，解析失败返回 None。
    """
    try:
        raw_pos = struct.unpack_from("<H", data, 0)[0]
        raw_spd = struct.unpack_from("<H", data, 2)[0]
        raw_trq = struct.unpack_from("<H", data, 4)[0]
        raw_tmp = struct.unpack_from("<H", data, 6)[0]
    except struct.error:
        return None

    # 从 CAN ID 提取模式和故障
    mode = (can_id_29 >> 22) & 0x03       # bits 22-23
    fault_flags = (can_id_29 >> 16) & 0x3F  # bits 16-21

    return MotorStatus(
        motor_id=motor_id,
        raw_position=raw_pos,
        raw_speed=raw_spd,
        raw_torque=raw_trq,
        raw_temp=raw_tmp,
        position_rad=_uint16_to_range(raw_pos, POS_RANGE_MIN, POS_RANGE_MAX),
        speed_rad_s=_uint16_to_range(raw_spd, SPD_RANGE_MIN, SPD_RANGE_MAX),
        torque_nm=_uint16_to_range(raw_trq, TORQUE_RANGE_MIN, TORQUE_RANGE_MAX),
        temperature=raw_tmp / TEMP_SCALE,
        mode=mode,
        fault_flags=fault_flags,
        timestamp=time.monotonic(),
    )


# ---------------------------------------------------------------------------
# 抽象后端接口
# ---------------------------------------------------------------------------

class _BaseCyberGearBackend:
    """CyberGear CAN 通信后端抽象基类。"""

    def __init__(self, master_id: int):
        self._master_id = master_id

    # ---- 连接管理 ----
    def connect(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    @property
    def is_connected(self) -> bool:
        raise NotImplementedError

    # ---- 发送指令 ----
    def send_motor_cmd(self, motor_id: int, comm_type: int, data: bytes = b"\x00" * 8):
        """发送电机指令 CAN 帧（抽象方法，由后端实现）。

        参数：
            motor_id: 电机 CAN ID。
            comm_type: 通信类型（COMM_* 常量）。
            data:      8 字节数据负载。
        """
        raise NotImplementedError

    # ---- SDO 读写（基类默认实现） ----
    def write_sdo_int(self, motor_id: int, index: int, value: int):
        """写 32 位整数 SDO。"""
        data = struct.pack("<HxxI", index, int(value))
        self.send_motor_cmd(motor_id, COMM_WRITE_SDO, data)

    def write_sdo_float(self, motor_id: int, index: int, value: float):
        """写 32 位浮点 SDO。"""
        data = struct.pack("<Hxx", index) + struct.pack("<f", float(value))
        self.send_motor_cmd(motor_id, COMM_WRITE_SDO, data)

    # ---- 快捷指令 ----
    def stop_motor(self, motor_id: int):
        """停止电机（清除错误、退出运控模式）。"""
        self.send_motor_cmd(motor_id, COMM_STOP)

    def enter_control_mode(self, motor_id: int):
        """进入运控模式。"""
        self.send_motor_cmd(motor_id, COMM_ENABLE)

    def set_zero(self, motor_id: int):
        """将电机当前位置设为机械零点。"""
        self.send_motor_cmd(motor_id, COMM_SET_ZERO, b"\x01\x00\x00\x00\x00\x00\x00\x00")


# ---------------------------------------------------------------------------
# USB-CAN 串口后端
# ---------------------------------------------------------------------------

class UsbCanSerialBackend(_BaseCyberGearBackend):
    """USB-CAN 串口 AT 协议后端。

    通过 USB 转 CAN 适配器（如 USB-CAN-A / USB-CAN-B）与电机通信。
    适配器需支持 AT 指令集（AT+CG 进入 CAN 透传模式，AT+CAN_BAUD 设置波特率）。

    反馈读取：后台线程持续读取串口，解析返回的 CAN 帧并触发回调。
    """

    def __init__(self, port: str, baud: int, master_id: int):
        super().__init__(master_id)
        self._port = port
        self._baud = baud
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_reader = threading.Event()
        # 回调函数列表：func(motor_status: MotorStatus) -> None
        self._feedback_callbacks: List[Callable[[MotorStatus], None]] = []

    # ---- 连接管理 ----

    def connect(self) -> None:
        """打开串口并初始化 CAN 适配器。"""
        with self._lock:
            self._ser = serial.Serial(self._port, self._baud, timeout=0.1)
            self._init_adapter()
            self._stop_reader.clear()
            self._reader_thread = threading.Thread(
                target=self._reader_loop, daemon=True, name="usb-can-reader"
            )
            self._reader_thread.start()

    def close(self) -> None:
        """停止读取线程并关闭串口。"""
        self._stop_reader.set()
        with self._lock:
            if self._ser is not None and self._ser.is_open:
                self._ser.close()
            self._ser = None

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._ser is not None and self._ser.is_open

    def register_feedback_callback(self, callback: Callable[[MotorStatus], None]) -> None:
        """注册电机反馈回调函数。"""
        self._feedback_callbacks.append(callback)

    def clear_feedback_callbacks(self) -> None:
        """释放 lifecycle 资源时清除回调对节点对象的引用。"""
        self._feedback_callbacks.clear()

    # ---- 适配器初始化 ----

    def _init_adapter(self) -> None:
        """发送 AT 指令初始化 CAN 适配器。"""
        init_cmds = [
            b"AT+CG\r\n",
            b"AT+CAN_BAUD=1000000\r\n",
            b"AT+AT\r\n",
        ]
        for cmd in init_cmds:
            self._ser.write(cmd)
            time.sleep(0.1)
            self._ser.read_all()

    # ---- 发送指令 ----

    def send_motor_cmd(self, motor_id: int, comm_type: int, data: bytes = b"\x00" * 8):
        """通过 USB-CAN 适配器发送 CAN 帧。"""
        with self._lock:
            if self._ser is None or not self._ser.is_open:
                raise RuntimeError("USB-CAN 串口未连接")
            can_id_29 = (comm_type << 24) | (self._master_id << 8) | motor_id
            wm_id_32 = (can_id_29 << 3) | 0x04
            id_bytes = struct.pack(">I", wm_id_32)
            frame = AT_PREAMBLE + id_bytes + bytes([len(data)]) + data + AT_TERMINATOR
            self._ser.write(frame)
            self._ser.flush()

    # ---- 反馈读取循环 ----

    def _reader_loop(self) -> None:
        """后台线程：持续读取串口返回的 CAN 帧并解析为 MotorStatus。"""
        buffer = bytearray()
        while not self._stop_reader.is_set():
            try:
                with self._lock:
                    if self._ser is None or not self._ser.is_open:
                        time.sleep(0.01)
                        continue
                    available = self._ser.in_waiting
                    if available <= 0:
                        time.sleep(0.001)
                        continue
                    chunk = self._ser.read(available)
            except (serial.SerialException, OSError):
                time.sleep(0.1)
                continue

            buffer.extend(chunk)

            while len(buffer) >= 7:
                at_idx = buffer.find(AT_PREAMBLE)
                if at_idx < 0:
                    buffer.clear()
                    break
                if at_idx > 0:
                    buffer = buffer[at_idx:]

                if len(buffer) < 7:
                    break

                dlc = buffer[5]
                waited_len = 2 + 4 + 1 + dlc
                if len(buffer) < waited_len + 2:
                    break

                if buffer[waited_len] != 0x0D or buffer[waited_len + 1] != 0x0A:
                    buffer = buffer[2:]
                    continue

                id_bytes = bytes(buffer[2:6])
                raw_id = struct.unpack(">I", id_bytes)[0]
                can_id_29 = raw_id >> 3
                comm_type = (can_id_29 >> 24) & 0xFF
                motor_id = (can_id_29 >> 8) & 0xFF
                data = bytes(buffer[6:6 + dlc])
                buffer = buffer[waited_len + 2:]

                if comm_type == COMM_GET_STATUS and dlc >= 8:
                    status = _parse_feedback_frame(motor_id, can_id_29, data)
                    if status is not None:
                        for cb in self._feedback_callbacks:
                            try:
                                cb(status)
                            except Exception:
                                pass


# ---------------------------------------------------------------------------
# SocketCAN 后端（微雪 2-CH CAN HAT+）
# ---------------------------------------------------------------------------

class SocketCanHatBackend(_BaseCyberGearBackend):
    """SocketCAN 后端（适配微雪 2-CH CAN HAT+ 等 MCP2515/MCP2518FD 扩展板）。

    使用 python-can 库通过标准 SocketCAN 接口与电机通信。

    反馈读取：使用 can.Bus 的 recv() 方法在后台线程中持续接收。
    """

    def __init__(self, channel: str, bustype: str, master_id: int):
        super().__init__(master_id)
        self._channel = channel
        self._bustype = bustype
        self._bus = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_reader = threading.Event()
        self._feedback_callbacks: List[Callable[[MotorStatus], None]] = []

    # ---- 连接管理 ----

    def connect(self) -> None:
        """打开 CAN 总线接口。"""
        if can is None:
            raise RuntimeError("未安装 python-can，无法使用 socketcan_hat 后端。"
                               "请执行: pip install python-can")
        self._bus = can.interface.Bus(channel=self._channel, bustype=self._bustype)
        self._stop_reader.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True, name="socketcan-reader"
        )
        self._reader_thread.start()

    def close(self) -> None:
        """关闭 CAN 总线接口。"""
        self._stop_reader.set()
        if self._bus is not None:
            try:
                self._bus.shutdown()
            finally:
                self._bus = None

    @property
    def is_connected(self) -> bool:
        return self._bus is not None

    def register_feedback_callback(self, callback: Callable[[MotorStatus], None]) -> None:
        """注册电机反馈回调函数。"""
        self._feedback_callbacks.append(callback)

    def clear_feedback_callbacks(self) -> None:
        """释放 lifecycle 资源时清除回调对节点对象的引用。"""
        self._feedback_callbacks.clear()

    # ---- 发送指令 ----

    def _build_can_id(self, comm_type: int, motor_id: int) -> int:
        """构造 29-bit 扩展 CAN ID。"""
        return (comm_type << 24) | (self._master_id << 8) | motor_id

    def send_motor_cmd(self, motor_id: int, comm_type: int, data: bytes = b"\x00" * 8):
        """通过 SocketCAN 发送 CAN 帧。"""
        if self._bus is None:
            raise RuntimeError("CAN 总线未连接")
        arbitration_id = self._build_can_id(comm_type, motor_id)
        payload = list(data[:8]) + [0x00] * max(0, 8 - len(data))
        msg = can.Message(
            arbitration_id=arbitration_id,
            data=payload[:8],
            is_extended_id=True,
        )
        self._bus.send(msg)

    # ---- 反馈读取循环 ----

    def _reader_loop(self) -> None:
        """后台线程：使用 can.Bus.recv() 接收 CAN 帧。

        仅处理通信类型为 0x02 的电机状态反馈帧。
        """
        while not self._stop_reader.is_set():
            if self._bus is None:
                time.sleep(0.01)
                continue
            try:
                msg = self._bus.recv(timeout=0.1)
            except Exception:
                time.sleep(0.01)
                continue

            if msg is None:
                continue

            can_id = msg.arbitration_id
            comm_type = (can_id >> 24) & 0xFF

            if comm_type == COMM_GET_STATUS and len(msg.data) >= 8:
                motor_id = (can_id >> 8) & 0xFF
                status = _parse_feedback_frame(motor_id, can_id, bytes(msg.data))
                if status is not None:
                    for cb in self._feedback_callbacks:
                        try:
                            cb(status)
                        except Exception:
                            pass


# ---------------------------------------------------------------------------
# CyberGear 驱动门面类
# ---------------------------------------------------------------------------

class CyberGearDriver:
    """CyberGear 电机驱动统一入口。

    封装两个后端（USB-CAN 串口 / SocketCAN），提供统一的：
      - 连接/断开
      - 发送运控指令
      - 电机反馈接收（通过回调）
      - 断线重连

    用法示例：
      driver = CyberGearDriver(backend="usb_can_serial", master_id=253, usb_port="/dev/ttyUSB0")
      driver.register_feedback_callback(my_callback)
      if driver.connect_with_retry():
          driver.enter_control_mode(1)
          driver.write_sdo_float(1, 0x7016, 0.5)
    """

    def __init__(
        self,
        backend: str,
        master_id: int,
        usb_port: str = "/dev/ttyUSB0",
        usb_baud: int = 921600,
        can_channel: str = "can0",
        can_bustype: str = "socketcan",
    ):
        self._backend_name = backend
        if backend == "usb_can_serial":
            self._impl = UsbCanSerialBackend(port=usb_port, baud=usb_baud, master_id=master_id)
        elif backend == "socketcan_hat":
            self._impl = SocketCanHatBackend(channel=can_channel, bustype=can_bustype, master_id=master_id)
        else:
            raise ValueError(f"不支持的后端类型: {backend}")

    @property
    def backend_name(self) -> str:
        return self._backend_name

    # ---- 连接管理 ----

    def connect(self) -> None:
        """直接连接（失败会抛异常）。"""
        self._impl.connect()

    def close(self) -> None:
        """断开连接。"""
        self._impl.close()

    @property
    def is_connected(self) -> bool:
        """当前是否已连接。"""
        return self._impl.is_connected

    def connect_with_retry(
        self,
        max_attempts: int = MAX_RECONNECT_ATTEMPTS,
        initial_delay: float = INITIAL_RECONNECT_DELAY,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """带指数退避重连的连接方法。

        参数：
            max_attempts: 最大重连次数
            initial_delay: 初始等待时间（秒）
            on_status: 状态回调（可选），接收 "connecting" / "reconnecting" / "failed"

        返回：
            连接成功返回 True，超过最大次数返回 False。
        """
        delay = initial_delay
        for attempt in range(max_attempts):
            try:
                if on_status:
                    on_status("connecting" if attempt == 0 else "reconnecting")
                self._impl.connect()
                return True
            except Exception:
                if on_status:
                    on_status("reconnecting")
                if attempt < max_attempts - 1:
                    time.sleep(delay)
                    delay = min(delay * RECONNECT_DELAY_MULTIPLIER, MAX_RECONNECT_DELAY)
        if on_status:
            on_status("failed")
        return False

    # ---- 反馈回调 ----

    def register_feedback_callback(self, callback: Callable[[MotorStatus], None]) -> None:
        """注册电机反馈回调。"""
        if hasattr(self._impl, "register_feedback_callback"):
            self._impl.register_feedback_callback(callback)

    def clear_feedback_callbacks(self) -> None:
        """清除后端反馈回调，避免 cleanup 后保留节点引用。"""
        if hasattr(self._impl, "clear_feedback_callbacks"):
            self._impl.clear_feedback_callbacks()

    # ---- 发送指令（委托给后端实现） ----

    def send_motor_cmd(self, motor_id: int, comm_type: int, data: bytes = b"\x00" * 8):
        """发送原始电机 CAN 指令帧。

        参数：
            motor_id: 电机 CAN ID。
            comm_type: 通信类型（COMM_* 常量）。
            data:      8 字节数据负载。
        """
        self._impl.send_motor_cmd(motor_id, comm_type, data)

    def write_sdo_int(self, motor_id: int, index: int, value: int):
        """写入 32 位整数型 SDO 参数。

        参数：
            motor_id: 电机 CAN ID。
            index:    SDO 索引地址。
            value:    整数值。
        """
        self._impl.write_sdo_int(motor_id, index, value)

    def write_sdo_float(self, motor_id: int, index: int, value: float):
        """写入 32 位浮点型 SDO 参数。

        参数：
            motor_id: 电机 CAN ID。
            index:    SDO 索引地址。
            value:    浮点值。
        """
        self._impl.write_sdo_float(motor_id, index, value)

    def stop_motor(self, motor_id: int):
        """停止电机（清除错误、退出运控模式）。

        参数：
            motor_id: 电机 CAN ID。
        """
        self._impl.stop_motor(motor_id)

    def enter_control_mode(self, motor_id: int):
        """进入运控模式（发送 COMM_ENABLE 帧）。

        参数：
            motor_id: 电机 CAN ID。
        """
        self._impl.enter_control_mode(motor_id)

    def set_zero(self, motor_id: int):
        """将电机当前位置设为机械零点。

        参数：
            motor_id: 电机 CAN ID。
        """
        self._impl.set_zero(motor_id)
