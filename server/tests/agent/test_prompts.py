"""Tests for the agent prompts module."""

from code_monet.agent.prompts import SYSTEM_PROMPT, build_system_prompt
from code_monet.types import DrawingStyleType, get_style_config


class TestBuildSystemPrompt:
    """Tests for build_system_prompt function."""

    def test_plotter_style_includes_monochrome_instructions(self) -> None:
        """Plotter style prompt mentions monochrome/black strokes."""
        style_config = get_style_config(DrawingStyleType.PLOTTER)
        prompt = build_system_prompt(style_config)

        assert "Plotter" in prompt
        assert "black" in prompt.lower()
        assert "blue" in prompt.lower()  # Human strokes appear blue

    def test_paint_style_includes_color_palette(self) -> None:
        """Paint style prompt includes color palette and brush presets."""
        style_config = get_style_config(DrawingStyleType.PAINT)
        prompt = build_system_prompt(style_config)

        assert "Paint" in prompt
        assert "oil_round" in prompt
        assert "watercolor" in prompt
        assert "mass_field" in prompt
        assert "tapered_band" in prompt
        assert "broken_edge" in prompt
        assert "Painterly Intelligence" in prompt
        assert "brush" in prompt.lower()
        # Should include color references
        assert "#" in prompt or "color" in prompt.lower()

    def test_paint_style_includes_human_color(self) -> None:
        """Paint style prompt mentions human stroke color (rose)."""
        style_config = get_style_config(DrawingStyleType.PAINT)
        prompt = build_system_prompt(style_config)

        assert "rose" in prompt.lower() or style_config.human_stroke.color in prompt

    def test_prompt_includes_canvas_dimensions(self) -> None:
        """Prompt includes canvas size information."""
        style_config = get_style_config(DrawingStyleType.PLOTTER)
        prompt = build_system_prompt(style_config)

        assert "800" in prompt
        assert "600" in prompt

    def test_prompt_includes_tool_documentation(self) -> None:
        """Prompt includes documentation for all tools."""
        style_config = get_style_config(DrawingStyleType.PLOTTER)
        prompt = build_system_prompt(style_config)

        assert "draw_paths" in prompt
        assert "generate_svg" in prompt
        assert "view_canvas" in prompt
        assert "imagine" in prompt
        assert "mark_piece_done" in prompt

    def test_prompt_includes_workflow_guidance(self) -> None:
        """Prompt includes 'how you work' guidance."""
        style_config = get_style_config(DrawingStyleType.PLOTTER)
        prompt = build_system_prompt(style_config)

        assert "Think out loud" in prompt
        assert "Look before you draw" in prompt

    def test_prompt_includes_collaboration_section(self) -> None:
        """Prompt includes collaboration guidance."""
        style_config = get_style_config(DrawingStyleType.PLOTTER)
        prompt = build_system_prompt(style_config)

        assert "Collaboration" in prompt
        assert "nudge" in prompt.lower()


class TestSystemPromptConstant:
    """Tests for backward compatibility constant."""

    def test_system_prompt_is_plotter_style(self) -> None:
        """SYSTEM_PROMPT constant is the plotter style prompt."""
        plotter_prompt = build_system_prompt(get_style_config(DrawingStyleType.PLOTTER))
        assert plotter_prompt == SYSTEM_PROMPT

    def test_system_prompt_is_string(self) -> None:
        """SYSTEM_PROMPT is a non-empty string."""
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 1000  # Substantial prompt
