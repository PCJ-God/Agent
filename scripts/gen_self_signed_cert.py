#!/usr/bin/env python
"""
生成自签 TLS 证书 —— 仅用于本地 / 内网验证 HTTPS。

生产环境请用 Let's Encrypt（见 docs/DEPLOY.md），不要拿自签证书对外：
浏览器不信任它，客户端还得关掉证书校验，等于绕过了 HTTPS 的意义。

用法:
    python scripts/gen_self_signed_cert.py
    python scripts/gen_self_signed_cert.py --host 10.0.0.5 --days 365
"""
import argparse
import ipaddress
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from src.config import PROJECT_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description="生成自签 TLS 证书（仅用于测试）")
    parser.add_argument(
        "--out", default=str(PROJECT_ROOT / "data" / "certs"), help="输出目录"
    )
    parser.add_argument("--days", type=int, default=365, help="有效期天数")
    parser.add_argument(
        "--host", action="append", default=[], help="额外的域名或 IP，可多次"
    )
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # SAN 里必须包含客户端实际访问用的名字，否则浏览器照样报错
    names = ["localhost", "127.0.0.1", "::1", *args.host]
    san: list[x509.GeneralName] = []
    for name in names:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            san.append(x509.DNSName(name))

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "deepcopilot-local-dev"),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=args.days))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    cert_path = out / "cert.pem"
    key_path = out / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    print(f"证书: {cert_path}")
    print(f"私钥: {key_path}   ← 别提交到 git，别外传")
    print(f"覆盖的名字: {', '.join(names)}")
    print(f"有效期: {args.days} 天")
    print("\n本地起 HTTPS:")
    print(f'  set SSL_CERTFILE={cert_path}')
    print(f'  set SSL_KEYFILE={key_path}')
    print("  python scripts/run_server.py")


if __name__ == "__main__":
    main()
