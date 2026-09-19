# Text and logo layout

For yellow artwork in CAD screenshots, add `ink_color:"yellow"` to the image item. This excludes black mechanical outlines and other non-yellow content inside the crop.

Uploaded PNG/JPEG/WebP artwork is supported with `kind:"image", image_base64:<base64 or data URL>, crop:[left,top,right,bottom], foreground:"auto", x:50,y:50,width:30,operation:"engrave"`. Use this object in a structural part's `markings` or in layout `items`. Crop coordinates are normalized 0..1 relative to the original image, origin top-left; placement is mm from the part bottom-left. Aspect ratio is preserved. Transparent images are traced from alpha so yellow-on-transparent strokes survive. Opaque artwork uses automatic light/dark foreground detection; explicit foreground and threshold are available. This is contour vectorization, not photographic grayscale engraving; inspect the generated preview before cutting. The original image is never replaced with a stock icon.

`create_design(preset="engraving_layout", parameters={"width_mm":300,"height_mm":400,"format":"both","items":[{"kind":"text","value":"PAYAS STEM","x":225,"y":375,"height":5,"align":"center"},{"kind":"path","d":"M0 0 L10 10 L20 0","x":225,"y":350,"width":30}]})`

Items use millimetres, origin bottom-left. Supported kinds: text, path, icon, line. Text supports Turkish characters through the existing outline font pipeline. Paths require actual vector data; unknown icon names raise an error instead of producing a plus sign. Set `closed:true` only for intentionally closed strokes. Bounds checks reject missing or off-sheet artwork instead of silently dropping it.

ENGRAVE presentation is yellow #FFFF00 in final SVG and ACI 2 in the DXF ENGRAVE layer; CUT is red/ACI 1. These are operation/layer colors, not a promise about material appearance or laser power. The existing review and production gate still apply. Imported screenshot logos need vectorization or original SVG/PLT input; the layout generator does not invent their geometry.
