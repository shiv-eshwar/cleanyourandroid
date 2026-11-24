"""Read-only local MCP interface for CleanYourAndroid."""

from . import audit as reporting
from .adb import Device, devices


def make_server():
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    server = FastMCP(
        "CleanYourAndroid",
        instructions="Inspect an authorized local Android device. Select an online serial from list_devices. "
                     "Use the local CLI and explicit human approval for any changes.",
    )
    readonly = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                               idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=readonly)
    def list_devices() -> list[dict]:
        """List local ADB devices and authorization state."""
        return devices()

    @server.tool(annotations=readonly)
    def audit_device(serial: str) -> dict:
        """Summarize storage, cache, optional packages, power, thermal, and recent CPU activity."""
        return reporting.audit(Device(serial))

    @server.tool(annotations=readonly)
    def diagnose_performance(serial: str) -> dict:
        """Read current Battery Saver, render rate, CPU, memory and thermal indicators."""
        return reporting.diagnostic_report(Device(serial))

    @server.tool(annotations=readonly)
    def standby_counters(serial: str) -> dict:
        """Read cumulative on-battery screen-off and Wi-Fi wakeup counters."""
        return reporting.standby(Device(serial))

    @server.tool(annotations=readonly)
    def app_frame_counters(serial: str, package: str) -> dict:
        """Read cumulative graphics counters for one app. Capture before and after an interaction."""
        return reporting.frame_stats(Device(serial), package)

    return server


def main():
    try:
        server = make_server()
    except ImportError as exc:
        raise SystemExit("Install the MCP extra with pip install '.[mcp]'.") from exc
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
