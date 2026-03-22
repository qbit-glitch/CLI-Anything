"""
pipelines.py — Composite multi-CLI pipeline tools registered with FastMCP.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session_bridge import SessionBridge


def register_pipelines(mcp, bridge: "SessionBridge", runner) -> None:
    """Register composite multi-CLI pipeline tools on *mcp*."""

    @mcp.tool(description="Convert image to 3D mesh then import into Blender for animation")
    def pipeline_image_to_3d_animation(
        image_path: str,
        output_dir: str,
        fps: int = 24,
        duration: float = 3.0,
    ) -> dict:
        """Full pipeline: image3d generate → blender import-mesh → basic animation setup."""
        results: dict = {}

        # Step 1: Generate mesh.  img_session is ephemeral (mesh gen only) —
        # always deleted before returning regardless of outcome.
        img_session = bridge.new_session("image3d")
        img_project = bridge.get_project_path(img_session)
        try:
            img_result = runner.run_cli_tool(
                "cli-anything-image3d",
                ["generate", image_path, "--output-dir", output_dir],
                img_project,
            )
        finally:
            bridge.delete_session(img_session)

        results["image3d"] = img_result
        if not img_result["success"]:
            return {"success": False, "step": "image3d", "results": results}

        # Step 2: Import mesh into Blender.
        mesh_path = img_result["data"].get("output_path", "")
        blend_session = bridge.new_session("blender")
        blend_project = bridge.get_project_path(blend_session)
        try:
            blend_result = runner.run_cli_tool(
                "cli-anything-blender",
                ["import-mesh", mesh_path],
                blend_project,
            )
            results["blender_import"] = blend_result

            # Step 3: Basic rotation animation (rotate 360 over duration)
            if blend_result["success"]:
                anim_result = runner.run_cli_tool(
                    "cli-anything-blender",
                    [
                        "animation", "keyframe",
                        "--property", "rotation_euler[2]",
                        "--frame", "1",
                        "--value", "0",
                    ],
                    blend_project,
                )
                results["animation"] = anim_result

            return {
                "success": blend_result.get("success", False),
                "session_id": blend_session,
                "results": results,
            }
        except Exception:
            # Unhandled exception — clean up blend_session since we can't return it.
            bridge.delete_session(blend_session)
            raise

    @mcp.tool(description="Create 3D text and export as video via Shotcut")
    def pipeline_text_to_video(
        text: str,
        output_path: str,
        duration: float = 5.0,
        style: str = "typewriter",
    ) -> dict:
        """Pipeline: blender text-3d → render → shotcut sequence."""
        results: dict = {}
        blend_session = bridge.new_session("blender")
        blend_project = bridge.get_project_path(blend_session)

        # Create 3D text in Blender
        text_result = runner.run_cli_tool(
            "cli-anything-blender",
            ["text3d", "create", "--text", text, "--animation", style],
            blend_project,
        )
        results["blender_text"] = text_result

        if not text_result["success"]:
            return {
                "success": False,
                "step": "blender_text",
                "session_id": blend_session,
                "results": results,
            }

        # Render to image sequence
        render_result = runner.run_cli_tool(
            "cli-anything-blender",
            ["render", "animation", "--output", output_path],
            blend_project,
        )
        results["render"] = render_result

        return {
            "success": render_result.get("success", False),
            "session_id": blend_session,
            "results": results,
        }
