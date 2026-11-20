# Oracle Cloud에서 토스증권 연결

Vercel의 토스 탭은 HTTPS로 Oracle VM에 조회를 요청합니다. 토스증권 키는 VM에 보관하고, Vercel과 VM은 별도의 중계 비밀값을 공유합니다.

## Oracle VM

1. OCI 콘솔의 **Compute → Instances → Create instance**에서 홈 리전의 **Always Free eligible** 인스턴스를 생성합니다. Ubuntu 24.04, A1 Flex 1 OCPU/6 GB 및 공인 IPv4가 있는 공용 서브넷을 사용할 수 있습니다. SSH 인바운드는 관리자의 IP에만 허용합니다.
2. **Networking → IP management → Reserved public IPs**에서 예약 공인 IPv4를 만들고 인스턴스의 VNIC 비공개 IP에 연결합니다. 기존 임시 IPv4를 먼저 해제해야 할 수 있습니다. 이후에는 예약 IP로 SSH에 접속합니다.
3. 토스증권 Open API 허용 IP 목록에 VM의 예약 IPv4를 추가합니다.
4. VM에 Git, Node.js 22.18 이상 및 Tailscale을 설치합니다. A1 Flex에는 ARM64 버전의 Node.js를 사용합니다. [Node.js 다운로드](https://nodejs.org/en/download) · [Tailscale 설치](https://tailscale.com/docs/install/linux)

## 중계 서비스

VM에 저장소를 복제하고, 토스 중계 변경이 있는 브랜치를 체크아웃합니다. 아래 예시에서는 Ubuntu 사용자로 `/home/ubuntu/stock`에 복제합니다. `command -v node`로 Node.js 경로를 확인합니다.

```sh
git clone https://github.com/YooJongWon/stock.git /home/ubuntu/stock
git -C /home/ubuntu/stock switch codex/toss-oracle-relay
openssl rand -hex 32
sudo install -m 600 /dev/null /etc/toss-relay.env
sudoedit /etc/toss-relay.env
```

생성한 무작위 값은 `TOSS_RELAY_SECRET`에 입력합니다. 아래 파일의 실제 값을 Git에 올리지 않습니다.

```dotenv
TOSS_CLIENT_ID=
TOSS_CLIENT_SECRET=
TOSS_RELAY_SECRET=
```

`/etc/systemd/system/toss-relay.service`를 다음 내용으로 작성합니다. `ExecStart`의 Node.js 위치는 위에서 확인한 경로를 사용합니다.

```ini
[Unit]
Description=Toss Securities read-only relay
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/stock/web
EnvironmentFile=/etc/toss-relay.env
ExecStart=/usr/bin/node /home/ubuntu/stock/web/relay/toss-relay.mts
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now toss-relay
curl -i http://127.0.0.1:8787/snapshot
sudo tailscale up
sudo tailscale funnel --bg 8787
sudo tailscale funnel status
```

인증 헤더가 없는 첫 `curl`은 HTTP 401을 반환합니다. Tailscale 로그인과 Funnel 활성화는 명령이 안내하는 링크에서 완료합니다. Funnel이 표시한 공개 HTTPS 주소의 `/snapshot`도 인증 없이 401을 반환하는지 확인합니다. Funnel을 사용하면 OCI에서 8787 포트를 공개할 필요가 없습니다. [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)

## Vercel

**Settings → Environment Variables → Production**에 `TOSS_RELAY_URL`로 Funnel의 HTTPS 주소, `TOSS_RELAY_SECRET`으로 VM과 같은 비밀값을 설정합니다. 배포 후 휴대폰에서 **토스 → 연결 확인**을 누릅니다. 조회에 성공하면 탭이 보이는 동안 30초마다 새로 조회합니다. 이미 Vercel에 토스 클라이언트 키를 등록했다면 중계 연결을 확인한 뒤 Vercel에서 제거할 수 있습니다.
