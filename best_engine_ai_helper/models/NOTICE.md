# Third-party model notice

`clip_nsfw_vit_l14.onnx` is a format conversion (TensorFlow SavedModel ->
ONNX, via `tf2onnx`) of the weights published at
[LAION-AI/CLIP-based-NSFW-Detector](https://github.com/LAION-AI/CLIP-based-NSFW-Detector)
(`clip_autokeras_binary_nsfw.zip`). No retraining was done; the weights are
numerically the same model, only the serialization format changed (verified
against the original TensorFlow SavedModel: mean scores match per category
to within ~0.01, and only 6 of 3199 samples in the original repo's own
manually-annotated test set flip their classification decision at this
project's 0.8 default threshold — see `best_engine_ai_helper/safety.py`'s
module docstring for the full evaluation).

Original license (MIT), reproduced in full:

```
Copyright 2022, Christoph Schuhmann

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to
deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.
```
