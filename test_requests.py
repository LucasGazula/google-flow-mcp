"""Corpos nativos: sementes, entradas e contexto sem submissão remota."""
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from flow_requests import _seed, image_request, video_request, upload_request


class RequestTest(unittest.TestCase):
    def test_video_edit_can_create_a_separate_workflow(self):
        project, source, workflow, output, new_workflow = (str(uuid4()) for _ in range(5))
        with patch("flow_requests._seed", side_effect=[("media-seed", output), ("workflow-seed", new_workflow)]):
            packet = video_request(project, "Edit", "abra_edit", "16:9", 1, "captcha",
                operation="edit", source_id=source, workflow_id=workflow,
                start_frame=0, end_frame=96, create_new_workflow=True)
        self.assertEqual(packet["rpc_id"], "jIps6")
        self.assertEqual(packet["params"][0][0][4], [None, None, None, None, "media-seed", "workflow-seed"])
        self.assertEqual(packet["request_workflow_ids"], [new_workflow])
        self.assertEqual(packet["request_media_ids"], [output])
        for operation, option in (("generate", True), ("extend", True), ("edit", 1)):
            with self.assertRaises(ValueError):
                video_request(project, "Edit", "abra_edit", "16:9", 1, "captcha",
                    operation=operation, source_id=source, workflow_id=workflow,
                    start_frame=0, end_frame=96, create_new_workflow=option)

    def test_seed_matches_frontend_sha256_uuid(self):
        with patch("flow_requests.uuid4", return_value=UUID("00000000-0000-0000-0000-000000000000")):
            seed, identifier = _seed()
        self.assertEqual(seed, "00000000-0000-0000-0000-000000000000")
        self.assertEqual(identifier, "12b9377c-be7e-4c94-a8a7-0d9d23929523")

    def test_image_references_and_edit_preserve_workflow(self):
        project, reference, source, workflow = (str(uuid4()) for _ in range(4))
        packet = image_request(project, "Prompt", "NARWHAL", "1:1", 2, "captcha", references=[reference])
        self.assertEqual(len(packet["params"][1]), 2)
        self.assertEqual(len(set(packet["request_media_ids"])), 2)
        for row in packet["params"][1]:
            self.assertEqual(row[2], [[reference, None, None, None, 1]])
            self.assertEqual(row[7][5], project)
            self.assertEqual(row[7][10], ["captcha", 1])
            self.assertEqual(row[8], [[[None, [[reference, reference]]], ["\n\nPrompt"]]])
        packet = image_request(project, "Edit", "NARWHAL", "1:1", 1, "captcha",
                               source_media_id=source, workflow_id=workflow)
        self.assertEqual(packet["params"][1][0][2], [[source, None, None, None, 2]])
        self.assertEqual(packet["params"][3][4], workflow)
        self.assertIsNone(packet["params"][3][7])
        self.assertIsNone(packet["params"][1][0][12])
        self.assertEqual(packet["request_workflow_ids"], [workflow])

    def test_image_request_with_character_entity_id_links_portrait(self):

        project, entity = str(uuid4()), str(uuid4())
        packet = image_request(project, "Portrait", "NARWHAL", "16:9", 1, "captcha", character_entity_id=entity)
        self.assertEqual(packet["rpc_id"], "ogiZ0b")
        self.assertEqual(packet["params"][4][1:], [None, [entity, [0]]])
        with self.assertRaises(ValueError):
            image_request(project, "Portrait", "NARWHAL", "16:9", 2, "captcha", character_entity_id=entity)


    def test_video_modes_and_upload_use_exact_input(self):
        project, start, end, reference = (str(uuid4()) for _ in range(4))
        with patch("flow_requests._seed",side_effect=[("media-seed",start),("workflow-seed",end)]):
            packet=video_request(project,"Prompt","model","16:9",1,"captcha")
        self.assertEqual(packet["params"][0][0][4][4:6],["media-seed","workflow-seed"])
        for kwargs, rpc, index in (({}, "YhhmEf", 4), ({"start_id":start}, "eb1hJf", 5),
                                  ({"start_id":start,"end_id":end}, "nprQif", 6),
                                  ({"references":[reference]}, "MZZa6b", 5)):
            packet = video_request(project, "Prompt", "model", "16:9", 2, "captcha", **kwargs)
            self.assertEqual(packet["rpc_id"], rpc)
            self.assertEqual(len(packet["params"][0]), 2)
            self.assertEqual(packet["params"][2][1], 2)
            self.assertEqual(len(packet["params"][0][0][index]), 6)
        for kwargs in ({"end_id":end}, {"references":[reference],"start_id":start}):
            with self.assertRaises(ValueError):
                video_request(project, "Prompt", "model", "16:9", 1, "captcha", **kwargs)
        with patch("flow_requests._seed",side_effect=[("media-seed",start),("workflow-seed",end)]):
            packet = upload_request(project, b"image", "image/png", "input.png", "captcha")
        self.assertEqual(packet["params"][10:12],["workflow-seed","media-seed"])
        self.assertEqual(packet["request_media_ids"],[start])
        self.assertEqual(packet["request_workflow_ids"],[end])
        self.assertEqual(packet["params"][1:4], ["aW1hZ2U=", "image/png", True])
        self.assertEqual(packet["params"][8], "input.png")
        with self.assertRaises(ValueError):
            upload_request(project, b"image", "image/png", "input.png", "")

    def test_video_edit_and_extend_keep_source_workflow_and_frame_bounds(self):
        project, source, workflow, output, unused = (str(uuid4()) for _ in range(5))
        for operation, rpc, index in (("edit", "jIps6", 4), ("extend", "fZytfe", 5)):
            with patch("flow_requests._seed",side_effect=[("media-seed",output),("workflow-seed",unused)]):
                packet = video_request(project,"Edit","model","16:9",1,"captcha",
                    operation=operation, source_id=source, workflow_id=workflow,
                    start_frame=24, end_frame=120)
            row = packet["params"][0][0]
            self.assertEqual(packet["rpc_id"],rpc)
            self.assertEqual(row[0],[None,source,24,120])
            self.assertEqual(row[index],[None,workflow,None,None,"media-seed"])
            self.assertEqual(packet["request_workflow_ids"],[workflow])
            self.assertEqual(packet["request_media_ids"],[output])
        for change in ({"count":2},{"start_frame":120},{"workflow_id":"../bad"}):
            arguments=dict(operation="edit",source_id=source,workflow_id=workflow,start_frame=24,end_frame=120,count=1)
            arguments.update(change)
            with self.assertRaises(ValueError):
                video_request(project,"Edit","model","16:9",captcha="captcha",**arguments)


if __name__ == "__main__":
    unittest.main()


class VoiceRequestTest(unittest.TestCase):
    def test_voice_is_appended_only_to_reference_generation(self):
        from flow_requests import video_request
        project, ref = str(uuid4()), str(uuid4())
        packet = video_request(project, "hello", "abra_r2v_4s", "16:9", 1, "token",
                               references=[ref], voice="Achernar")
        row = packet["params"][0][0]
        self.assertEqual(packet["rpc_id"], "MZZa6b")
        self.assertEqual(row[1], [[None, ref]])
        self.assertEqual(row[6:], [None, [["achernar"]]])
        for kwargs in ({}, {"references":[ref], "voice":"bad name"}):
            with self.assertRaises(ValueError):
                video_request(project, "hello", "abra_t2v_4s", "16:9", 1, "token", **({"voice":"achernar"} | kwargs))

    def test_character_ingredient_matches_captured_row(self):
        from flow_requests import video_request
        project, entity = str(uuid4()), str(uuid4())
        packet = video_request(project, "walks", "abra_r2v_4s", "16:9", 1, "token",
                               characters=[entity], voice="Achernar")
        row = packet["params"][0][0]
        self.assertEqual(packet["rpc_id"], "MZZa6b")
        self.assertIsNone(row[1])
        self.assertEqual(row[6:], [None, [["achernar"]], None, [[entity]]])
        with self.assertRaises(ValueError):
            video_request(project, "walks", "abra_i2v", "16:9", 1, "token",
                          start_id=str(uuid4()), characters=[entity])

