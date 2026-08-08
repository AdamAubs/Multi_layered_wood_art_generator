"""Run-specific prompt for producing an accurate Etsy listing guide."""

from __future__ import annotations

from pathlib import Path

from release_tools.run_facts import INCHES_PER_MM, ReleaseFacts


def write_etsy_handoff(path: Path, facts: ReleaseFacts, release_name: str, release_version: str, zip_details: list[dict[str, object]]) -> None:
    width_mm, height_mm = facts.dimensions_mm
    zips = "\n".join(f"  - {item['name']}: {item['size']} bytes" for item in zip_details) or "  - No archive created"
    warnings = "\n".join(f"  - {warning}" for warning in facts.warnings) or "  - No metadata conflicts found."
    layer_stems = "\n".join(f"  - {layer.stem}" for layer in facts.layers)
    path.write_text(f"""# Etsy Release Handoff

You are helping the seller create one accurate Etsy instant-download listing from this release. Treat the verified facts below as read-only. First interview the seller for every required unknown. Do not invent product subject, tested materials, compatibility, price, licensing exceptions, AI involvement, or intellectual-property rights. After the seller answers, produce the complete `ETSY_LISTING_GUIDE.md` defined below.

## Verified Facts

```yaml
project_id: {facts.project_id or 'unknown'}
run_id: {facts.run_id or 'unknown'}
original_input_basename: {facts.original_filename or 'unknown'}
release_name: {release_name}
release_version: {release_version}
visible_artwork_layers: {len(facts.art_layers)}
optional_mounting_layers: {len(facts.cleat_layers)}
total_delivered_layers: {len(facts.layers)}
dxf_svg_units: millimeters
outside_dimensions_mm: [{width_mm:.3f}, {height_mm:.3f}]
outside_dimensions_inches: [{width_mm * INCHES_PER_MM:.3f}, {height_mm * INCHES_PER_MM:.3f}]
source_png_pixels: [{facts.source_pixels[0]}, {facts.source_pixels[1]}]
recorded_dpi: {facts.dpi if facts.dpi else 'unknown'}
combined_layout: one DXF and one matching SVG containing every delivered layer in a neat 10 mm-spaced grid
french_cleats_included: {'yes' if facts.cleat_layers else 'no'}
license_limit: 100 finished physical products
physical_fabrication_evidence: seller will provide photos of the completed physical artwork; seller confirmation required before making a production-test claim
```

Delivered layer stems:
{layer_stems}

Buyer ZIP files:
{zips}

Metadata conflicts or missing facts:
{warnings}

Seller media includes composite images, showcase images, and front/rear Etsy exploded MP4s with posters when the release completed successfully.

## Physical Fabrication Evidence

The seller will provide photos they took of the completed physical artwork. Ask the seller to confirm that the pictured artwork was cut from this release's delivered files, identify the machine, material, thickness, and any relevant production changes, and identify which photos may be used in the listing. Treat the photos and the seller's confirmation as evidence that this design was physically fabricated, rather than merely generated digitally. Do not claim a production test, machine compatibility, material compatibility, or exact fabrication result until the seller confirms those facts.

## Reference-Driven Showcase Images

The seller may provide original reference images for the design and for the desired presentation. Ask which images may be used as visual references and which may be published. Use them to identify the piece's subject, palette, material character, mood, era, setting, and intended buyer. Then create a concise showcase-image brief for each proposed image: composition, environment, props, camera angle, crop, lighting direction, color temperature, and the exact design details that must remain faithful to the delivered files.

Make the showcase environment match the piece's specific vibe rather than using a generic workshop or stock scene. Prefer bright, intentional lighting that reveals the wood grain, cut edges, layer depth, and finish: soft directional key light, controlled fill, and enough separation from the background for clear listing thumbnails. Use the seller's actual physical photos when available. If proposing generated or composited lifestyle media, label it as new media to create, do not portray it as a physical photo, and do not alter fixed text, protected marks, layer count, colors, or other verified design details.

## Mandatory Seller Interview

Ask a compact first round covering:

1. The plain-language subject, intended product name, style, and important visual elements.
2. Fixed text, names, dates, logos, team marks, characters, brands, or anything that could be mistaken for personalization.
3. The physical-artwork photos they will provide, whether the pictured piece was cut from these delivered files, the machine, material/thickness, actual finished size, relevant production changes, and whether cleat layers were tested at that thickness.
4. Software and machines actually tested. Do not infer compatibility from extensions.
5. Likely buyer, project/occasion, and accurate buyer search phrases.
6. Seller-selected price, quantity, SKU, and shop section.
7. Whether AI was used in concept imagery or delivered design content, with enough detail for accurate Etsy disclosure.
8. Ownership or permission for every protected name, logo, character, photo, and design element. If uncertain, flag IP review and do not say publication is safe.
9. Which original reference images and completed-artwork photos are available, which may be used publicly, and the desired showcase mood, setting, and lighting.

Ask targeted follow-ups only where answers are incomplete or conflict with the verified facts.

## Research And Truth Rules

When browsing is available, verify current Etsy limits, fields, category wording, and SEO guidance from official Etsy sources before finalizing. Separate platform facts from suggestions. Do not claim live search volume, competition, or comparative pricing without a source and date. Use the most specific accurate digital cutting-template category, not shipped wall decor.

Do not claim personalized, editable, commercial use, tested compatibility, or included supplies unless supported. Etsy AI disclosure must be truthful. Flag IP risk, especially sports teams/logos and entertainment characters, without making a legal determination. Keep titles within current Etsy limits; prefer human-readable SEO. Use 13 distinct relevant multiword tags and validate each against Etsy's current tag length limit.

## Required `ETSY_LISTING_GUIDE.md`

Produce all of these sections: Publish status (`READY`, `READY AFTER LISTED FIXES`, or `DO NOT PUBLISH YET`) with reasons; verified product summary; one suggested title plus up to two alternatives with character and word counts; a paste-ready description beginning `DIGITAL DOWNLOAD ONLY`; 13 validated tags; category and attributes; price, quantity, SKU, and shop section; listing-media order; reference-driven showcase-image briefs with environment and lighting direction; image alt text; video plan; digital-download disclosures; AI disclosure; intellectual-property review; upload checklist; and final pre-publish checklist.

The finished description must explain per-layer DXF/SVG geometry, the 10 mm-spaced combined all-layer DXF/SVG reference, PNG references, assembly images, dimensions/scaling, visible versus mounting layers, confirmed physical-fabrication evidence when supplied, tested facts only, exclusions, fixed-text/personalization limits, the 100-finished-product license, and accurate AI/IP disclosures. Do not invent refund or shop policies.
""", encoding="utf-8")