import copy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from flow_capabilities import parse_capabilities, parse_model_statuses, quote_configuration, read_capabilities


def catalog_fixture():
    video = [None] * 24
    video[0], video[4], video[7] = "veo_3_1_t2v_lite", [[1, [[None, 10]]], [2, [[None, 10]]]], [[[[1]]]]
    video[12], video[16], video[23] = [[2, 1]], 8, [[1]]
    image = [None] * 22
    image[0], image[4], image[8] = "NARWHAL", [[2, [[None, 0]]]], [[[[1]], [[1, 4]]]]
    image[13] = [[1, 2, 3, 4, 5, 2, 3]]
    catalog = [None] * 8
    catalog[4] = [["Veo 3.1 - Lite", [video], True, "veo_3_1_lite"]]
    catalog[5] = [["Nano Banana 2", [image], None, "narwhal_display"]]
    return [catalog]


class CapabilityTest(unittest.IsolatedAsyncioTestCase):
    def test_catalog_preserves_real_zero_and_applies_plan_status_and_format(self):
        data = catalog_fixture()
        states = parse_model_statuses([[["veo_3_1_lite", 1]]])
        modes = parse_capabilities(data, 2, states)
        video = modes["video"]["models"][0]["variants"][0]
        self.assertEqual(video["credits_per_output"], 10)
        self.assertEqual(video["aspects"], ["16:9", "9:16"])
        self.assertEqual(video["duration_seconds"], 8)
        self.assertEqual(video["resolutions"], ["720p"])
        self.assertTrue(video["available"])
        image = modes["image"]["models"][0]["variants"][0]
        self.assertEqual(image["credits_per_output"], 0)
        self.assertEqual(image["aspects"], ["1:1", "9:16", "16:9", "3:4", "4:3"])
        self.assertEqual(image["input_feature_codes"], [[1], [1, 4]])
        missing = parse_capabilities(data, 3, {})["video"]["models"][0]["variants"][0]
        self.assertIsNone(missing["credits_per_output"])
        self.assertFalse(missing["available"])
        data[0][4][0][1][0][4] = [[2, [None, []]]]
        unavailable = parse_capabilities(data, 2, {})["video"]["models"][0]["variants"][0]
        self.assertIsNone(unavailable["credits_per_output"])
        data[0][4][0][1][0][4] = [[2, [[]]]]
        self.assertEqual(parse_capabilities(data, 2, {})["video"]["models"][0]["variants"][0]["credits_per_output"], 0)
        blocked = parse_model_statuses([[["veo_3_1_lite", 3]]])
        self.assertFalse(parse_capabilities(data, 2, blocked)["video"]["models"][0]["variants"][0]["available"])
        self.assertTrue(parse_model_statuses([[["model", 2, [[1, 1]]]]])["model"]["blocked"])
        self.assertFalse(parse_model_statuses([[["model", 2]]])["model"]["blocked"])

    def test_unknown_schema_and_plan_never_become_free_supported_generation(self):
        for tier in (None, True, 0, 4, "2"):
            with self.assertRaises(ValueError):
                parse_capabilities(catalog_fixture(), tier, {})
        for value in (None, [], {}, [[["../bad", 1]]], [[["model", True]]], [[["model", 4]]]):
            with self.assertRaises(ValueError):
                parse_model_statuses(value)
        for field, value in ((4, [[2, [[None, -1]]]]), (4, [[2, [[None, True]]]]),
                             (12, [[99]]), (16, -1), (23, [[99]]), (0, "../private")):
            data = copy.deepcopy(catalog_fixture())
            data[0][4][0][1][0][field] = value
            with self.assertRaises(ValueError):
                parse_capabilities(data, 2, {})

    def test_native_quote_preserves_model_features_duration_and_budget(self):
        caps={"modes":parse_capabilities(catalog_fixture(),2,{}),"service_tier_code":2,"observed_at":"now"}
        base=dict(aspect="16:9",count=2,max_credits=20,features=[1],duration_seconds=8)
        self.assertEqual(quote_configuration(caps,"veo-lite",**base)["quoted_credits"],20)
        for change in ({"max_credits":19},{"duration_seconds":4},{"features":[1,5]},
                       {"resolution":"1080p"},{"count":True}):
            with self.assertRaises(ValueError):
                quote_configuration(caps,"veo-lite",**{**base,**change})
        with self.assertRaises(ValueError):
            quote_configuration(caps,"veo-fast",**base)
        self.assertEqual(quote_configuration(caps,"nano-banana-2",aspect="1:1",count=2,
            max_credits=0,features=[1,4])["quoted_credits"],0)

    def test_omni_360p_requires_catalog_variant_and_its_own_price(self):
        data = catalog_fixture()
        variant = copy.deepcopy(data[0][4][0][1][0])
        variant[0] = "abra_t2v_360p"
        variant[4] = [[2, [[None, 4]]]]
        variant[23] = [[4]]
        data[0][4].append(["Omni Flash", [variant], True, "abra"])
        caps = {"modes": parse_capabilities(data, 2, {}), "service_tier_code": 2,
                "observed_at": "now"}
        args = dict(aspect="16:9", count=2, max_credits=8, features=[1],
                    duration_seconds=8, resolution="360p")
        quote = quote_configuration(caps, "omni-flash", **args)
        self.assertEqual((quote["model_key"], quote["quoted_credits"]), ("abra_t2v_360p", 8))
        with self.assertRaises(ValueError):
            quote_configuration(caps, "omni-flash", **{**args, "max_credits": 7})
        with self.assertRaises(ValueError):
            quote_configuration(caps, "veo-lite", **args)

    def test_video_high_resolution_uses_the_catalog_variant_key(self):
        data = catalog_fixture()
        for code, resolution in ((2, "1080p"), (3, "4k")):
            variant = copy.deepcopy(data[0][4][0][1][0])
            variant[0] = f"veo_lite_t2v_8s_{resolution}"
            variant[23] = [[code]]
            data[0][4][0][1].append(variant)
        caps = {"modes": parse_capabilities(data, 2, {}), "service_tier_code": 2,
                "observed_at": "now"}
        for resolution in ("1080p", "4k"):
            quote = quote_configuration(caps, "veo-lite", aspect="16:9", count=1,
                max_credits=10, features=[1], duration_seconds=8, resolution=resolution)
            self.assertEqual(quote["model_key"], f"veo_lite_t2v_8s_{resolution}")

    def test_nano_banana_2_lite_uses_catalog_id_not_display_label(self):
        data = catalog_fixture()
        lite = copy.deepcopy(data[0][5][0][1][0])
        lite[0] = "nano_banana_2_lite_key"
        data[0][5].append(["🍌 Nano Banana 2 Lite", [lite], None, "harbor_seal"])
        caps = {"modes": parse_capabilities(data, 2, {}), "service_tier_code": 2,
                "observed_at": "now"}
        quote = quote_configuration(caps, "nano-banana-2-lite", aspect="1:1", count=2,
            max_credits=0, features=[1, 4])
        self.assertEqual(quote["model_key"], "nano_banana_2_lite_key")
        with self.assertRaises(ValueError):
            quote_configuration({**caps, "modes": parse_capabilities(catalog_fixture(), 2, {})},
                "nano-banana-2-lite", aspect="1:1", count=1, max_credits=0, features=[1])

    async def test_http_capabilities_confirm_project_and_keep_private_fields_out(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
            ["project", ["Private title"]], [936,1,2,2,None,936,None],
            [[["veo_3_1_lite",1]]], catalog_fixture()]), close=AsyncMock())
        result = await read_capabilities("conta-a", "project", client=client)
        self.assertEqual(result["source"], "HTTP/HTrJv")
        self.assertEqual(result["service_tier_code"], 2)
        self.assertNotIn("Private title", str(result))
        self.assertEqual(client.rpc.await_count, 4)
        client.close.assert_not_awaited()
        client.rpc.reset_mock()
        client.rpc.side_effect = [["other", ["Private"]]]
        with self.assertRaises(ValueError):
            await read_capabilities("conta-a", "project", client=client)
        self.assertEqual(client.rpc.await_count, 1)
        with self.assertRaises(ValueError):
            await read_capabilities("conta-other", "project", client=client)


if __name__ == "__main__":
    unittest.main()
