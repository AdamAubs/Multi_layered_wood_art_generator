Platform: GPT-4o image generation is the best fit here. It handles flat illustration styles and symbolic/decorative motifs very reliably, and you can iterate quickly.

Try these prompts:

1. Japanese Mon (family crest) style

"A traditional Japanese kamon family crest, circular symmetrical design, flat vector illustration, exactly 4 distinct solid colors, bold black outlines, crane and pine branch motifs, cream background, no gradients, no texture, no shading, clean graphic art style"

This works well because kamon are specifically designed to be single-color cut patterns — they're essentially pre-designed for your use case. The circular symmetry also gives your greedy algorithm a favorable topology where the frame touches the outermost ring on all sides.

2. Art Nouveau botanical poster

"Art Nouveau decorative poster, stylized lotus flower with geometric border, exactly 3 flat solid colors: deep teal, warm gold, cream white, bold outlines, symmetrical left-right composition, no gradients, no photorealism, poster illustration style, William Morris influenced"

Specifying exactly 3 colors in the prompt pre-aligns the image with what your pipeline will find. Art Nouveau has naturally large flat fill regions separated by decorative outlines, which gives K-means clean distinct clusters.

3. Geometric mandala with cultural motifs

"Tibetan mandala design, flat geometric illustration, 4 solid fill colors only: deep red, navy blue, gold, ivory white, radial symmetry, lotus petal border, vajra center symbol, no gradients no shadows no texture, clean vector art style, black outlines"

Mandalas have radial symmetry like your Chinese pattern but with even harder color boundaries. The specified color count directly guides what K-means should find.

Prompting Techniques That Help Your Pipeline
Explicitly name your color count. Saying "exactly 4 distinct solid colors" nudges the generator toward the separation your preprocessor expects. Without this, generators tend to introduce 15-20 subtle shades.

Forbid gradients and texture explicitly. "No gradients, no texture, no shading, no photorealism" in the negative space of the prompt is more reliable than just asking for flat color. These are the exact properties that cause pyrMeanShiftFiltering to struggle.

Request radial or bilateral symmetry. Symmetric designs naturally produce layers where opposite sides of the image share the same color patches at equal distances from the frame — which is exactly the condition where your nearest-first traversal performs best.

Ask for bold outlines. Outlines create hard edges between color regions in pixel space, which means K-means cluster boundaries fall on actual design boundaries rather than cutting through gradient transitions mid-shape.

Keep composition centered and framed. Your algorithm uses a rectangular frame border as the starting safe zone, so designs with a clear outer boundary element (ring, border, decorative frame) that physically touches all four sides of the canvas will give the greedy algorithm a strong first layer with zero bridge cost.
