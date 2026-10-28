"""rb-drift-config：解析 deploy.json 并按接口约定断言。"""

from __future__ import annotations

import json


def check_deploy(ctx):
    if not ctx.exists("out/deploy.json"):
        return False, "out/deploy.json 不存在"
    try:
        data = json.loads(ctx.read("out/deploy.json"))
    except json.JSONDecodeError as exc:
        return False, f"不是合法 JSON: {exc}"
    if data.get("port") != 9091:
        return False, f"port 期望 9091（漂移后配置），实际 {data.get('port')!r}"
    if data.get("host") != "0.0.0.0":
        return False, f"host 期望 0.0.0.0，实际 {data.get('host')!r}"
    return True, "port=9091, host=0.0.0.0"
