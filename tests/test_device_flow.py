import unittest
from unittest.mock import patch

from bootstrap import device_flow


class DeviceFlowTests(unittest.TestCase):
    def test_begin_requires_expected_verification_uri(self):
        payload = {
            "device_code": "opaque-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }
        with patch.object(device_flow, "_post_form", return_value=payload):
            result = device_flow.begin_device_authorization()
        self.assertEqual(result.user_code, "ABCD-EFGH")
        self.assertEqual(result.interval, 5)

    def test_begin_rejects_untrusted_verification_uri(self):
        payload = {
            "device_code": "opaque-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://example.invalid/steal-code",
            "expires_in": 900,
            "interval": 5,
        }
        with patch.object(device_flow, "_post_form", return_value=payload):
            with self.assertRaises(device_flow.DeviceFlowError):
                device_flow.begin_device_authorization()

    def test_authorize_falls_back_to_manual_code_when_qr_is_unavailable(self):
        authorization = device_flow.DeviceAuthorization(
            "opaque-device-code", "ABCD-EFGH",
            "https://github.com/login/device", 900, 1
        )
        with patch.object(device_flow, "begin_device_authorization", return_value=authorization), \
             patch.object(device_flow, "_show_qr", side_effect=device_flow.DeviceFlowError("no qrencode")), \
             patch.object(device_flow, "wait_for_access_token", return_value="memory-only-token") as wait, \
             patch("builtins.print") as output:
            token = device_flow.authorize()
        self.assertEqual(token, "memory-only-token")
        wait.assert_called_once_with(authorization)
        printed = " ".join(str(call.args) for call in output.call_args_list)
        self.assertIn("ABCD-EFGH", printed)
        self.assertIn("https://github.com/login/device", printed)

    def test_wait_returns_bearer_token_without_logging_it(self):
        with patch.object(
            device_flow,
            "_post_form",
            return_value={"access_token": "test-secret-token", "token_type": "bearer"},
        ):
            token = device_flow.wait_for_access_token(
                device_flow.DeviceAuthorization(
                    "opaque-device-code", "ABCD-EFGH",
                    "https://github.com/login/device", 900, 1
                ),
                sleep=lambda _seconds: None,
            )
        self.assertEqual(token, "test-secret-token")

    def test_wait_rejects_non_bearer_token(self):
        with patch.object(
            device_flow,
            "_post_form",
            return_value={"access_token": "test-token", "token_type": "mac"},
        ):
            with self.assertRaises(device_flow.DeviceFlowError):
                device_flow.wait_for_access_token(
                    device_flow.DeviceAuthorization(
                        "opaque-device-code", "ABCD-EFGH",
                        "https://github.com/login/device", 900, 1
                    ),
                    sleep=lambda _seconds: None,
                )


if __name__ == "__main__":
    unittest.main()
