# [동시 실행] 용 예제.
#
# '# --- GO ---' 윗부분은 준비다. import openpibo 처럼 무거운 건 여기서 끝낸다.
# 로봇마다 import 시간이 달라서, 이걸 안 나누면 시작이 수백 ms 씩 어긋난다.
# 전부 준비되면 커넥터가 UDP 트리거를 한 방 쏘고, 그 순간 아랫부분이 같이 돈다.

from openpibo.motion import Motion
from openpibo.device import Device

m = Motion()
d = Device()
d.eye_on(0, 0, 0)

# --- GO ---

d.eye_on(0, 100, 255)
m.set_motion('hello', 1)
m.set_motion('dance1', 2)
d.eye_off()
print('done')
