import unittest

import local_inference_v4 as inference


class LocalInferenceV4Tests(unittest.TestCase):
    def setUp(self):
        self.rule = (
            "когда заряд аккумулятора Альфы опускается ниже 10 процентов, "
            "устройство Альфа отключается."
        )

    def test_correct_device_below_threshold(self):
        state = "текущий заряд аккумулятора Альфы составляет 7 процентов."
        self.assertIsNotNone(inference.infer(self.rule, state))

    def test_other_device_is_not_mistaken_for_target(self):
        state = "текущий заряд аккумулятора Беты составляет 7 процентов."
        self.assertIsNone(inference.infer(self.rule, state))

    def test_missing_subject_is_rejected(self):
        state = "текущий заряд аккумулятора составляет 7 процентов."
        self.assertIsNone(inference.infer(self.rule, state))

    def test_value_above_threshold_does_not_trigger(self):
        state = "текущий заряд аккумулятора Альфы составляет 12 процентов."
        self.assertIsNone(inference.infer(self.rule, state))

    def test_threshold_boundary_does_not_trigger(self):
        state = "текущий заряд аккумулятора Альфы составляет 10 процентов."
        self.assertIsNone(inference.infer(self.rule, state))

    def test_explicit_device_form_is_supported(self):
        state = "заряд устройства Альфа составляет 7 процентов."
        self.assertIsNotNone(inference.infer(self.rule, state))

    def test_other_explicit_device_is_rejected(self):
        state = "заряд устройства Бета составляет 7 процентов."
        self.assertIsNone(inference.infer(self.rule, state))


if __name__ == "__main__":
    unittest.main()
