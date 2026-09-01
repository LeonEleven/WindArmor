# Algorithm Getting Started

这是一条面向 WindArmor 新算法开发者的“第一天”路径。示例开发机为 Intel Mac；它主要用于
算法开发和软件验证。机器人的正式运行平台仍是 Raspberry Pi 5、Ubuntu 24.04 和 ROS 2
Jazzy。

本教程不需要 Raspberry Pi 或机器人硬件，也不得访问真实 CAN、GPIO、PWM、串口、电机或
风扇。完成后，你应该能够：从 `develop` 创建 `feature/algo-*` 分支，理解
`FlightState -> Controller -> FlightCommand`，运行现有算法测试，编写一个小型控制器及其
pytest，执行 synthetic DRY_RUN 和完整软件 CI，并向 `develop` 提交 Pull Request。

正式 API、安全边界和评审规范以[算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)为准；本文只
回答新人第一天如何把开发流程跑通。

## 1. What you will learn

```text
FlightState
    |
    v
Flight Controller
    |
    v
FlightCommand
    |
    v
Runtime / Safety
    |
    v
Hardware
```

算法开发者的主要接口是 `FlightState -> FlightCommand`。控制器读取不可变的状态快照，返回
一个完整控制意图；Runtime 和安全层决定该意图能否继续下发。

算法层不拥有硬件，也不应直接访问 CAN、GPIO、串口、PWM、硬件 SDK、ROS 硬件资源或控制
权服务。单元测试和 synthetic DRY_RUN 的输出都只是软件结果。

## 2. Intel macOS development environment

先确认 CPU 架构：

```bash
uname -m
```

本文示例中的 Intel Mac 应输出 `x86_64`。安装 Apple 命令行工具，并使用 Homebrew 安装 Git
和 Python 3.12：

```bash
xcode-select --install
brew install git python@3.12

python3.12 --version
git --version
```

若尚未安装 Homebrew，请先按 [Homebrew 官方安装说明](https://brew.sh/)安装。Python 3.12 与
正式平台 Ubuntu 24.04 的系统 Python 版本一致，也满足当前纯算法代码需要。

macOS 是这里的 Python/算法开发环境，不是 WindArmor 正式 ROS 2 Jazzy 部署平台。更接近
正式 Linux/ROS 环境的验证放在第 11 节的 Docker 容器中完成。

## 3. Clone WindArmor

```bash
mkdir -p ~/Projects
cd ~/Projects

git clone https://github.com/LeonEleven/WindArmor.git
cd WindArmor

git fetch --all --tags --prune
git switch develop
git pull --ff-only origin develop
```

`master` 保存稳定发布基线；算法日常开发从最新 `develop` 开始，不直接在 `master` 或
`develop` 上提交。

## 4. Create an algorithm feature branch

为一个可独立 review 的算法任务创建一个短期分支：

```bash
git switch -c feature/algo-my-controller
```

推荐路径是：

```text
develop
   |
   v
feature/algo-*
   |
   v
Pull Request
   |
   v
develop
```

不要把多个无关算法或顺手重构混进同一分支，也不要直接向 `master` 或 `develop` push。

## 5. Create the Python development environment

当前仓库没有独立的 `requirements.txt`、`pyproject.toml` 或锁文件。Flight 包的 ROS 依赖由
`package.xml`/`rosdep` 管理；本节的纯算法测试只额外需要 `pytest`。

```bash
python3.12 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install pytest
```

后续每次打开新终端，在仓库根目录执行：

```bash
source .venv/bin/activate
```

这里不需要在 macOS 原生安装 ROS 2，也不需要安装任何硬件驱动。

## 6. Read these files first

按下面顺序阅读；所有路径均相对于仓库根目录：

1. [`docs/ALGORITHM_DEVELOPER_GUIDE.md`](ALGORITHM_DEVELOPER_GUIDE.md)：正式算法 API、输入
   语义、安全边界与评审检查表；
2. [`docs/FLIGHT_CONTROL_API.md`](FLIGHT_CONTROL_API.md)：完整接口与单位契约；
3. [`src/windarmor_flight_control/windarmor_flight_control/core/models.py`](../src/windarmor_flight_control/windarmor_flight_control/core/models.py)：
   `FlightState`、`FlightCommand` 和嵌套数据模型；
4. [`src/windarmor_flight_control/windarmor_flight_control/core/controller.py`](../src/windarmor_flight_control/windarmor_flight_control/core/controller.py)：
   `reset()`/`update()` 控制器协议；
5. [`src/windarmor_flight_control/windarmor_flight_control/algorithms/example_algorithm_controller.py`](../src/windarmor_flight_control/windarmor_flight_control/algorithms/example_algorithm_controller.py)：
   不依赖 ROS/硬件的教学控制器；
6. [`src/windarmor_flight_control/windarmor_flight_control/runtime/controller_loader.py`](../src/windarmor_flight_control/windarmor_flight_control/runtime/controller_loader.py)：
   `module.path:factory` 加载契约；
7. [`src/windarmor_flight_control/windarmor_flight_control/testing.py`](../src/windarmor_flight_control/windarmor_flight_control/testing.py)：
   fake、stale 和 unobserved 状态 helper；
8. [`src/windarmor_flight_control/windarmor_flight_control/synthetic_dry_run.py`](../src/windarmor_flight_control/windarmor_flight_control/synthetic_dry_run.py)：
   纯软件 DRY_RUN 入口；
9. [`src/windarmor_flight_control/test/test_example_algorithm_controller.py`](../src/windarmor_flight_control/test/test_example_algorithm_controller.py)
   和 [`test_synthetic_dry_run.py`](../src/windarmor_flight_control/test/test_synthetic_dry_run.py)：
   可复制的测试风格和无硬件边界断言。

不要以 `bounded_verification_controller.py` 作为新人模板；它服务于受限版本/硬件验证。

## 7. Run the existing example algorithm tests

从仓库根目录、已激活的 `.venv` 中运行：

```bash
PYTHONPATH=src/windarmor_flight_control \
python -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_example_algorithm_controller.py -q
```

这是 Level 1 纯软件验证。它直接构造内存中的 `FlightState`，不需要 ROS graph，不创建 node，
也不访问任何硬件。

## 8. Run synthetic DRY_RUN

运行仓库现有的确定性软件演示：

```bash
PYTHONPATH=src/windarmor_flight_control \
python -m windarmor_flight_control.synthetic_dry_run
```

也可以指定 synthetic 相对俯仰角（单位 rad）：

```bash
PYTHONPATH=src/windarmor_flight_control \
python -m windarmor_flight_control.synthetic_dry_run \
  --pitches -0.20 -0.10 0.0 0.10 0.20
```

该入口通过真实 controller factory 加载教学控制器，但所有输入都是 fake/synthetic
`FlightState`。输出应持续显示：

```text
dispatch: preview only; authority=NONE; actuation_allowed=false
```

最后一个 stale 场景应返回不带电机/风扇载荷的 safe-stop。该命令不导入 `rclpy`、不启动
ROS、没有硬件控制权，也不读取 `/dev`。不要用
`flight_control_dry_run.launch.py` 替代它；那个 launch 需要外部状态发布者，不是本教程的
纯软件默认入口。

## 9. Build your first controller

下面是一个小型教学示例。它读取相对俯仰角，对 `left_pitch` 产生有界偏移，其他电机保持
首次有效反馈基线，两路风扇保持零请求。输入未知、过期、无效或 `dt` 非法时，它清除基线并
fail closed 到 `FlightCommand.safe_stop()`。

在自己的 `feature/algo-*` 分支中，可把它保存为
`src/windarmor_flight_control/windarmor_flight_control/algorithms/my_pitch_controller.py`：

```python
import math

from windarmor_flight_control.core.models import (
    FanCommand,
    FlightCommand,
    FlightState,
)


class MyPitchController:
    def __init__(self, required_motor_names):
        self.motor_names = tuple(required_motor_names)
        if (
            not self.motor_names
            or len(set(self.motor_names)) != len(self.motor_names)
            or "left_pitch" not in self.motor_names
        ):
            raise ValueError("unique motor names including left_pitch are required")
        self.baseline = None

    def reset(self):
        self.baseline = None

    def _safe_stop(self):
        self.baseline = None
        return FlightCommand.safe_stop()

    @staticmethod
    def _finite_number(value):
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
        )

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        pitch = state.imu.relative_pitch_rad
        if (
            not self._finite_number(dt)
            or float(dt) <= 0.0
            or not self._finite_number(pitch)
            or state.system.e_stop_active is not False
            or not state.system.required_inputs_fresh
            or not state.imu.valid
            or not state.imu.fresh
            or set(state.motors) != set(self.motor_names)
        ):
            return self._safe_stop()

        positions = {}
        for name in self.motor_names:
            motor = state.motors[name]
            if (
                not self._finite_number(motor.position_rad)
                or not motor.has_feedback
                or not motor.valid
                or not motor.fresh
                or not motor.healthy
            ):
                return self._safe_stop()
            positions[name] = float(motor.position_rad)

        if self.baseline is None:
            self.baseline = positions

        correction_rad = max(-0.02, min(0.02, 0.10 * float(pitch)))
        targets = dict(self.baseline)
        targets["left_pitch"] += correction_rad
        return FlightCommand(
            motor_positions_rad=targets,
            fan_commands=FanCommand(left=0.0, right=0.0),
        )


def create_controller(required_motor_names, configuration=None):
    del configuration
    return MyPitchController(required_motor_names)
```

这段 Markdown 示例不是新的正式控制器，`0.10` 和 `0.02 rad` 也不是飞行调参、机械边界或
硬件授权值。生产实现还应按[算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)处理构造参数、
逻辑电机名称和完整审查要求。算法模块不得 import ROS、CAN、GPIO、串口、PWM 或硬件 SDK。

## 10. Unit testing the controller

将测试放在 `src/windarmor_flight_control/test/test_my_pitch_controller.py`。下面的短例子使用
仓库 helper 覆盖中性、正负输入、有界输出、stale 输入和非法 `dt`：

```python
from dataclasses import replace

import pytest

from windarmor_flight_control.algorithms.my_pitch_controller import MyPitchController
from windarmor_flight_control.core.models import FlightCommand
from windarmor_flight_control.core.validation import validate_flight_command
from windarmor_flight_control.testing import (
    make_fake_flight_state,
    make_stale_flight_state,
)


MOTORS = ("left_lift", "left_pitch", "right_pitch", "right_lift")


def state_with_pitch(pitch_rad):
    state = make_fake_flight_state(MOTORS)
    return replace(
        state,
        imu=replace(
            state.imu,
            pitch_rad=pitch_rad,
            relative_pitch_rad=pitch_rad,
        ),
    )


@pytest.mark.parametrize(
    ("pitch_rad", "expected"),
    [(0.0, 0.0), (0.10, 0.01), (-0.10, -0.01), (10.0, 0.02)],
)
def test_pitch_response_is_signed_and_bounded(pitch_rad, expected):
    command = MyPitchController(MOTORS).update(state_with_pitch(pitch_rad), 0.02)
    validate_flight_command(command, MOTORS)
    assert command.motor_positions_rad["left_pitch"] == pytest.approx(expected)


@pytest.mark.parametrize("dt", [0.0, -0.01, float("nan")])
def test_invalid_dt_fails_closed(dt):
    command = MyPitchController(MOTORS).update(state_with_pitch(0.1), dt)
    assert command == FlightCommand.safe_stop()


def test_stale_input_requests_payload_free_safe_stop():
    command = MyPitchController(MOTORS).update(
        make_stale_flight_state(MOTORS), 0.02
    )
    assert command == FlightCommand.safe_stop()
```

运行自己的测试：

```bash
PYTHONPATH=src/windarmor_flight_control \
python -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_my_pitch_controller.py -q
```

除上面示例外，正式算法测试至少还应覆盖：deadband（若有）、正负边界、输出完整性、reset 后
重新捕获基线、`None`/非有限输入、E-stop/无效状态，以及 safe-stop 不携带任何执行器载荷。

## 11. ROS 2 Jazzy validation on Intel Mac

macOS 上完成 Python 迭代后，使用 Docker Desktop 的 Linux amd64 ROS 2 Jazzy 环境执行更
接近正式平台的软件验证。先确认 Docker 可用：

```bash
docker --version
```

从仓库根目录拉取并进入 ROS 官方镜像：

```bash
docker pull --platform linux/amd64 ros:jazzy-ros-base-noble

docker run --rm -it \
  --platform linux/amd64 \
  -v "$PWD":/workspace/WindArmor \
  -w /workspace/WindArmor \
  ros:jazzy-ros-base-noble \
  bash
```

该容器没有 `--privileged`、没有映射 `/dev`，也不应增加 CAN/GPIO/串口设备映射。容器内
执行：

```bash
source /opt/ros/jazzy/setup.bash

rosdep update
rosdep install \
  --from-paths src \
  --ignore-src \
  --rosdistro jazzy \
  -r \
  -y

./scripts/ci_software.sh
```

`ci_software.sh` 是当前仓库的完整纯软件 CI 入口：执行安全/whitespace 检查、Python 编译、
五包 `colcon build`、pure/fake/mock 测试和结果汇总。也可在排查构建问题时手工运行：

```bash
colcon build --symlink-install
source install/setup.bash
colcon test --packages-select \
  imu_cybergear_ros2 \
  windarmor_fan_controller \
  windarmor_interfaces \
  windarmor_flight_control \
  windarmor_bringup
colcon test-result --verbose
```

只有在运行前确认新增/修改测试仍隔离硬件 I/O，才可继续使用这些命令。软件 CI PASS 只表示
软件构建与 fake/mock 验证通过：**Software CI PASS != Hardware PASS**。

## 12. Before submitting a PR

从仓库根目录先检查改动并重跑与你的风险相称的软件验证：

```bash
git status --short --branch
git diff --check
git diff

PYTHONPATH=src/windarmor_flight_control \
python -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_my_pitch_controller.py -q

PYTHONPATH=src/windarmor_flight_control \
python -m windarmor_flight_control.synthetic_dry_run
```

在 ROS 2 Jazzy Linux 环境中再执行 `./scripts/ci_software.sh`，并把准确结果写入 PR。然后提交
和 push 当前 feature 分支：

```bash
git add \
  src/windarmor_flight_control/windarmor_flight_control/algorithms/my_pitch_controller.py \
  src/windarmor_flight_control/test/test_my_pitch_controller.py
git commit -m "feat(flight-control): add my pitch controller"
git push -u origin feature/algo-my-controller
```

在 GitHub 创建 `feature/algo-my-controller -> develop` 的 Pull Request，不要以 `master` 为
目标。PR 应说明输入/输出、单位、限幅、失效后安全行为、执行过的测试、软件 CI 结果，以及
`Hardware not executed`。等待 maintainer review 和适用的 required checks；不要直接 push
或自行 merge 到 `develop`。

## 13. What algorithm developers must NOT do

正常算法开发阶段不得自行：

- 操作真实 CAN、GPIO、PWM 或串口；
- 直接控制电机、风扇、ESC 或硬件 SDK；
- 打开 Flight takeover、请求 authority 或争用 ROS 硬件 ownership；
- 绕过 Runtime、安全校验、看门狗、软限位或命令租约；
- 修改、清除或弱化 `/e_stop` 行为；
- 启动硬件 node/launch，或进行未经独立明确授权的硬件测试；
- 把 pure/fake/mock、DRY_RUN、Docker 或 CI 结果描述为 Hardware PASS；
- 直接向 `master`/`develop` push，或向 `master` 提交普通算法 PR。

边界、数据语义、控制权和 Level 3 移交要求见
[算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)。

## 14. Suggested learning path

```text
Level 1
Pure Python + unit tests
        |
        v
Level 2
Synthetic DRY_RUN + software integration
        |
        v
PR to develop
        |
        v
Maintainer review
        |
        v
Level 3
Authorized hardware validation
```

Level 3 是单独的维护者/operator 流程。它需要新的硬件范围、安全计划和用户明确授权；完成
本教程、合入 `develop` 或软件 CI PASS 都不会自动进入 Level 3。
