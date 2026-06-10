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
        assert "background_wash" in prompt
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
        """Prompt tells the agent to use the provided canvas size."""
        style_config = get_style_config(DrawingStyleType.PLOTTER)
        prompt = build_system_prompt(style_config)

        assert "current canvas size is provided" in prompt
        assert "Origin (0,0) is top-left" in prompt

    def test_prompt_includes_tool_documentation(self) -> None:
        """Prompt includes documentation for all tools."""
        style_config = get_style_config(DrawingStyleType.PLOTTER)
        prompt = build_system_prompt(style_config)

        assert "draw_paths" in prompt
        assert "generate_svg" in prompt
        assert "view_canvas" in prompt
        assert "imagine" in prompt
        assert "mark_piece_done" in prompt

    def test_prompt_includes_reference_translation_guidance(self) -> None:
        """Prompt encodes transferable reference translation instead of one-off recipes."""
        style_config = get_style_config(DrawingStyleType.PAINT)
        prompt = build_system_prompt(style_config)

        assert "Visual Reference Translation" in prompt
        assert "dominant silhouette" in prompt
        assert "Counter-shape" in prompt
        assert "Sector roles" in prompt
        assert "Failure modes" in prompt
        assert "sector_bounds" in prompt
        assert "contour_stack" in prompt
        assert "edge_fingers" in prompt
        assert "curved_ribbon_mass" in prompt
        assert "crescent_mass" in prompt
        assert "small_figure_silhouette" in prompt
        assert "small_figure_with_prop" in prompt
        assert "First-pass contract" in prompt
        assert "not as a full-composition template" in prompt
        assert "Do not call the piece perfect" in prompt
        assert "critique_canvas" in prompt
        assert "Do not sign or mark done after a failing critique" in prompt
        assert "separate filled masses" in prompt
        # No subject-specific recipes: the prompt teaches operations, not templates.
        assert "breaking_wave_masses" not in prompt
        assert "hooked_counterform_masses" not in prompt
        assert "Japanese woodblock" not in prompt

    def test_prompt_includes_tool_error_recovery_guidance(self) -> None:
        """Prompt tells the agent to simplify tool calls instead of giving up."""
        style_config = get_style_config(DrawingStyleType.PLOTTER)
        prompt = build_system_prompt(style_config)

        assert "not proof that the drawing system is broken" in prompt
        assert "Use `draw_paths` with 1-5 valid paths" in prompt
        assert "Never tell the human you are blocked by infrastructure" in prompt

    def test_prompt_includes_dense_batch_guidance(self) -> None:
        """Prompt tells the agent it can draw many intentional marks at once."""
        style_config = get_style_config(DrawingStyleType.PAINT)
        prompt = build_system_prompt(style_config)

        assert "large coherent batches" in prompt
        assert "Dozens or hundreds of `draw_paths` paths" in prompt
        assert "many timid trickle calls" in prompt

    def test_prompt_includes_layering_guidance(self) -> None:
        """Prompt tells the agent to establish a colored ground before details."""
        style_config = get_style_config(DrawingStyleType.PAINT)
        prompt = build_system_prompt(style_config)

        assert "do not start on raw white" in prompt
        assert "color-filled ground" in prompt
        assert "Layer in this order" in prompt
        assert "the painting is not layered yet" in prompt
        assert "not compete with equal-detail background noise" in prompt

    def test_prompt_does_not_force_imagine_for_known_references(self) -> None:
        """Known references and small assets should start with drawing tools."""
        style_config = get_style_config(DrawingStyleType.PAINT)
        prompt = build_system_prompt(style_config)

        assert "Do not use `imagine` as a reflexive first move" in prompt
        assert "known visual references" in prompt
        assert "small assets" in prompt
        assert "start directly with `generate_svg`" in prompt

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
