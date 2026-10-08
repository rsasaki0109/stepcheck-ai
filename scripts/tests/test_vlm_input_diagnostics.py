"""Input integrity checks using asymmetric RGB patches, not model accuracy fixtures."""

from pathlib import Path
import importlib.util
from types import SimpleNamespace
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diagnose_local_vlm import inspect_input


class VisionInputTest(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("torch") and importlib.util.find_spec("numpy"),
                         "Install the local VLM extra to check tensor reconstruction.")
    def test_asymmetric_rgb_patches_keep_location_and_channel_order(self):
        import torch
        import numpy as np
        from PIL import Image

        colors = [(255,0,0), (0,255,0), (0,0,255), (51,101,201)]
        patches = np.zeros((4,3,2,14,14), dtype=np.float32)
        for index,color in enumerate(colors):
            for channel,value in enumerate(color):
                patches[index,channel] = value
        processor = SimpleNamespace(image_processor=SimpleNamespace(patch_size=14,
            merge_size=2,temporal_patch_size=2,do_normalize=False,do_rescale=False))
        inputs = {'image_grid_thw':torch.tensor([[1,2,2]]),
                  'pixel_values':torch.tensor(patches.reshape(4,-1)),
                  'input_ids':torch.tensor([[99]])}
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)/'input.png'
            report = inspect_input(inputs,processor,destination,99)
            image = np.array(Image.open(destination))
            for position,color in zip([(0,0),(0,14),(14,0),(14,14)],colors):
                self.assertEqual(tuple(image[position]),color)
            self.assertEqual(report['image_token_count'],1)
            inputs['input_ids'] = torch.tensor([[99,99]])
            with self.assertRaises(ValueError):
                inspect_input(inputs,processor,destination,99)

    @unittest.skipUnless(importlib.util.find_spec("torch") and importlib.util.find_spec("numpy"),
                         "Install the local VLM extra to check tensor reconstruction.")
    def test_video_temporal_pairs_preserve_frame_order(self):
        import torch
        import numpy as np
        from PIL import Image

        colors = [(255,0,0),(0,255,0),(0,0,255),(255,255,0)]
        patches = np.zeros((2,4,3,2,14,14),dtype=np.float32)
        for index,color in enumerate(colors):
            for channel,value in enumerate(color):
                patches[index//2,:,channel,index%2] = value
        processor = SimpleNamespace(video_processor=SimpleNamespace(patch_size=14,
            merge_size=2,temporal_patch_size=2,do_normalize=False,do_rescale=False))
        inputs = {'video_grid_thw':torch.tensor([[2,2,2]]),
                  'pixel_values_videos':torch.tensor(patches.reshape(8,-1)),
                  'input_ids':torch.tensor([[77,77]])}
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)/'video.png'
            report = inspect_input(inputs,processor,destination,77,modality='video')
            image = np.array(Image.open(destination))
            for index,color in enumerate(colors):
                self.assertEqual(tuple(image[0,index*224]),color)
            self.assertEqual(report['reconstructed_frame_count'],4)


if __name__ == '__main__':
    unittest.main()
