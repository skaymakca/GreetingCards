# Plan: Improving Text Rendering in AI-Generated Greeting Cards

## Problem

The `--full-card` mode in `scripts/generate_sample_cards.py` asks OpenAI gpt-image-1 to generate entire greeting cards as images, including family names and greeting text baked into the design. The text quality is poor — misspellings, garbled characters, and inconsistent typography are common with gpt-image-1.

## Current Setup

- Model: `gpt-image-1`
- Size: `1024x1536` (portrait)
- Quality: `low` (default in our script)
- Text is included in the image prompt and rendered by the AI model

## Option 1: Upgrade to gpt-image-1.5 (recommended first step)

**Effort: minimal** — change the model string, no new SDK needed.

gpt-image-1.5 launched December 2025 with significantly better text rendering — denser, smaller, more accurate characters. It has the highest LM Arena score (1264).

### Changes needed

- Change `model="gpt-image-1"` to `model="gpt-image-1.5"` in `generate_image_openai()`
- Bump default quality to `"high"` (default for 1.5, improves text fidelity)
- Add a `--image-model` CLI flag to make the model configurable

### Prompt tips from OpenAI's 1.5 prompting guide

- Put literal text in **quotes or ALL CAPS** in the prompt
- Spell out tricky words letter-by-letter for accuracy
- Specify typography details (font style, size, color, placement) as constraints
- For brand names or uncommon spellings, be very explicit

### References

- [GPT Image 1.5 Prompting Guide (OpenAI Cookbook)](https://cookbook.openai.com/examples/multimodal/image-gen-1.5-prompting_guide)
- [GPT Image 1.5 Model docs](https://platform.openai.com/docs/models/gpt-image-1.5)
- [OpenAI Images API Reference](https://platform.openai.com/docs/api-reference/images)

## Option 2: Ideogram 3.0 via Together AI

**Effort: moderate** — new SDK dependency, different API shape.

Ideogram 3.0 (March 2025) is purpose-built for text rendering accuracy (~90%) by former Google Brain researchers. Best-in-class for typography, logos, posters, and marketing materials with text. Supports custom grid systems, margin padding, and text flow.

### Changes needed

- Add `together` or use Ideogram's own API
- New `generate_image_ideogram()` function
- CLI flag to select image provider (`--image-provider openai|ideogram`)

### References

- [Ideogram 3.0 Features](https://ideogram.ai/features/3.0)
- [Ideogram 3.0 API on Together AI](https://www.together.ai/models/ideogram-3-0)

## Option 3: Google Imagen 4 via Vertex AI

**Effort: moderate-high** — requires GCP setup, Vertex AI SDK.

Imagen 4 delivers first-class text rendering with strong multi-line layout handling. Good option if already in the Google ecosystem.

### Changes needed

- Add `google-cloud-aiplatform` dependency
- GCP project + Vertex AI setup
- New image generation function

## Option 4: Hybrid approach (AI image + PyMuPDF text overlay)

**Effort: moderate** — rework the full-card pipeline.

Generate only the visual/photo elements with AI, then overlay text using PyMuPDF (as the standard mode already does). This guarantees perfect text but loses the "integrated design" aesthetic of full-card mode.

Could be a middle ground: generate the card *background/art* with AI, then composite crisp vector text on top before rasterizing.

## Model Comparison

| Model | Text Accuracy | API Access | Quality | Cost |
|-------|--------------|------------|---------|------|
| gpt-image-1 (current) | Poor | OpenAI API | Good photos | Low |
| **gpt-image-1.5** | Good | OpenAI API (drop-in) | Best overall | Medium |
| **Ideogram 3.0** | Best (~90%) | Together AI / Ideogram API | Great for text-heavy | Medium |
| Google Imagen 4 | Good | Vertex AI (GCP) | Strong | Medium |
| FLUX.2 | Good | Replicate, fal.ai | Best photorealism | Medium |

## Recommended Path

1. **Immediate**: Switch to `gpt-image-1.5` + `quality="high"` + improved prompts (Option 1)
2. **If still insufficient**: Add Ideogram 3.0 as an alternative provider (Option 2)
3. **Fallback**: Hybrid approach for guaranteed text accuracy (Option 4)
