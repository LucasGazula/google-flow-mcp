"""Testes locais do CRUD de personagens sem autenticação Flow."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from flow_character import manage_character, list_voice_presets


class CharacterTest(unittest.IsolatedAsyncioTestCase):
    def test_voice_preset_catalog_is_not_claimed_account_verified(self):
        result = list_voice_presets()
        self.assertEqual(result["status"], "catalog_only")
        self.assertFalse(result["verified_for_account"])
        self.assertTrue(any(voice["name"] == "Zephyr" for voice in result["voices"]))

    async def test_native_character_create_success_and_uncertain_handling(self):
        project, entity, image = str(uuid4()), str(uuid4()), str(uuid4())
        empty_payload = [None, [], [], [], None, [], None, None]
        created_row = [project, entity, None, [1, "Kai", []], None, None]
        linked_row = [project, entity, None, [1, "Kai", [[[image]]]], None, None]
        created_payload = [None, [], [], [], None, [created_row], None, None]
        linked_payload = [None, [], [], [], None, [linked_row], None, None]
        assets = [{"media_id": image, "workflow_id": str(uuid4()), "kind": "image"}]

        with patch("asyncio.sleep", AsyncMock()), \
             patch("flow_assets.parse_assets", return_value=assets):
            # Criação com sucesso
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
                empty_payload,
                {},
                created_payload,
                {},
                linked_payload,
            ]))
            result = await manage_character("conta-a", project, "create", display_name="Kai",
                                            image_media_id=image, client=client)
            self.assertEqual(result["status"], "created")
            self.assertEqual(result["character"]["display_name"], "Kai")
            self.assertEqual(result["character"]["entity_id"], entity)
            self.assertEqual(result["character"]["reference_media_ids"], [image])

            # Verifica parâmetros de C4BZMd
            client.rpc.assert_any_await("C4BZMd", params=[[project, None, None, [1, "Kai", []]]])

            # Verifica parâmetros de Sc7aEb
            sc7_calls = [c for c in client.rpc.await_args_list if c.args[0] == "Sc7aEb"]
            self.assertEqual(len(sc7_calls), 1)
            sc7_params = sc7_calls[0].kwargs["params"]
            self.assertEqual(sc7_params[:9], [image, None, None, project, None, None, None,
                                              [None, None, [entity, [0]]], None])

            # Criação incerta: C4BZMd falha/leitura não traz o personagem
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
                empty_payload,
                {},
            ] + [empty_payload] * 6))
            result = await manage_character("conta-a", project, "create", display_name="Kai",
                                            image_media_id=image, client=client)
            self.assertEqual(result["status"], "submission_unknown")
            self.assertFalse(result["retry_automatically"])
            self.assertEqual([c.args[0] for c in client.rpc.await_args_list].count("C4BZMd"), 1)
            self.assertEqual([c.args[0] for c in client.rpc.await_args_list].count("Sc7aEb"), 0)

    async def test_native_character_create_from_description(self):
        project, entity = str(uuid4()), str(uuid4())
        empty_payload = [None, [], [], [], None, [], None, None]
        created_row = [project, entity, None, [1, "Faroleiro", []], None, None]
        created_payload = [None, [], [], [], None, [created_row], None, None]
        linked_row = [project, entity, None, [1, "Faroleiro", [[[str(uuid4())]]]], None, None]
        linked_payload = [None, [], [], [], None, [linked_row], None, None]

        with patch("asyncio.sleep", AsyncMock()), \
             patch("flow_video.generate_images", new_callable=AsyncMock) as mock_gen_img:
            mock_gen_img.return_value = {"status": "completed", "job_id": "job-portrait-123"}
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
                empty_payload,
                {},
                created_payload,
                linked_payload,
            ]))
            result = await manage_character("conta-a", project, "create", display_name="Faroleiro",
                                            description="Um velho faroleiro", max_credits=0, client=client)
            self.assertEqual(result["status"], "created")
            self.assertEqual(result["portrait_job_id"], "job-portrait-123")
            self.assertEqual(result["character"]["display_name"], "Faroleiro")
            self.assertEqual(result["character"]["entity_id"], entity)
            mock_gen_img.assert_awaited_once_with(
                "conta-a", "Um velho faroleiro", 0, project,
                model="nano-banana-2", aspect="16:9", count=1,
                character_entity_id=entity, client=client
            )

            # Validações de entradas conflitantes e faltantes
            unopened = SimpleNamespace(account_id="conta-a", rpc=AsyncMock())
            with self.assertRaises(ValueError):
                await manage_character("conta-a", project, "create", display_name="Faroleiro",
                                       image_media_id=str(uuid4()), description="Um velho faroleiro",
                                       max_credits=0, client=unopened)
            with self.assertRaises(ValueError):
                await manage_character("conta-a", project, "create", display_name="Faroleiro",
                                       description="Um velho faroleiro", client=unopened)
            with self.assertRaises(ValueError):
                await manage_character("conta-a", project, "create", display_name="Faroleiro",
                                       description="Um velho faroleiro", max_credits="zero", client=unopened)
            unopened.rpc.assert_not_awaited()


    async def test_native_character_rename_and_delete(self):
        project, entity, image = str(uuid4()), str(uuid4()), str(uuid4())
        initial_row = [project, entity, None, [1, "Old Name", [[[image]]]], None, None]
        renamed_row = [project, entity, None, [1, "New Name", [[[image]]]], None, None]
        initial_payload = [None, [], [], [], None, [initial_row], None, None]
        renamed_payload = [None, [], [], [], None, [renamed_row], None, None]
        empty_payload = [None, [], [], [], None, [], None, None]

        with patch("asyncio.sleep", AsyncMock()):
            # Rename com parâmetros exatos
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
                initial_payload, {}, renamed_payload
            ]))
            result = await manage_character("conta-a", project, "rename", entity_id=entity,
                                            display_name="New Name", client=client)
            self.assertEqual(result["status"], "updated")
            client.rpc.assert_any_await("rzMKMb", params=[
                [project, entity, None, [1, "New Name"]], [["entity_info.display_name"]]
            ])

            # Delete sem confirmação -> confirmation_required sem RPC
            unopened_client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock())
            result = await manage_character("conta-a", project, "delete", entity_id=entity,
                                            confirm_delete=False, client=unopened_client)
            self.assertEqual(result["status"], "confirmation_required")
            unopened_client.rpc.assert_not_awaited()

            # Delete com sucesso -> deleted
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
                initial_payload, {}, empty_payload
            ]))
            result = await manage_character("conta-a", project, "delete", entity_id=entity,
                                            confirm_delete=True, client=client)
            self.assertEqual(result["status"], "deleted")
            client.rpc.assert_any_await("cz8Z4b", params=[None, None, project, [entity]])

    async def test_native_character_update_voice_and_personality(self):
        project, entity, image = str(uuid4()), str(uuid4()), str(uuid4())
        initial_row = [project, entity, None, [1, "Lake keeper", [[[image]]]], None, None]
        updated_row = [project, entity, None, [1, "Lake keeper", [[[image]], [[None, "achernar"]], "Guardião"]], None, None]
        initial_payload = [None, [], [], [], None, [initial_row], None, None]
        updated_payload = [None, [], [], [], None, [updated_row], None, None]

        with patch("asyncio.sleep", AsyncMock()):
            # Update apenas voz
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
                initial_payload, {}, updated_payload
            ]))
            result = await manage_character("conta-a", project, "update", entity_id=entity,
                                            voice="Achernar", client=client)
            self.assertEqual(result["status"], "updated")
            client.rpc.assert_any_await("rzMKMb", params=[
                [project, entity, None, [1, None, [None, [[None, "achernar"]]]]],
                [["entity_info.character_info.audio_references"]]
            ])

            # Update apenas personalidade
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
                initial_payload, {}, updated_payload
            ]))
            result = await manage_character("conta-a", project, "update", entity_id=entity,
                                            personality="Guardião", client=client)
            self.assertEqual(result["status"], "updated")
            client.rpc.assert_any_await("rzMKMb", params=[
                [project, entity, None, [1, None, [None, None, "Guardião"]]],
                [["entity_info.character_info.personality_notes"]]
            ])

            # Update combinado com confirmação por leitura
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
                initial_payload, {}, updated_payload
            ]))
            result = await manage_character("conta-a", project, "update", entity_id=entity,
                                            display_name="Lake keeper", voice="Achernar",
                                            personality="Guardião", client=client)
            self.assertEqual(result["status"], "updated")
            self.assertEqual(result["character"]["voice"], "achernar")
            self.assertEqual(result["character"]["personality"], "Guardião")
            client.rpc.assert_any_await("rzMKMb", params=[
                [project, entity, None, [1, "Lake keeper", [None, [[None, "achernar"]], "Guardião"]]],
                [["entity_info.display_name", "entity_info.character_info.audio_references", "entity_info.character_info.personality_notes"]]
            ])

            # Erros de validação
            unopened = SimpleNamespace(account_id="conta-a", rpc=AsyncMock())
            with self.assertRaises(ValueError):
                await manage_character("conta-a", project, "update", entity_id=entity,
                                       voice="invalid_voice", client=unopened)
            with self.assertRaises(ValueError):
                await manage_character("conta-a", project, "create", display_name="Kai",
                                       image_media_id=image, voice="Achernar", client=unopened)
            unopened.rpc.assert_not_awaited()

    def test_parse_characters_with_image_voice_and_personality(self):
        from flow_character import parse_characters
        project, entity, image, thumb = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
        row = [project, entity, None, [1, "Lake keeper", [[[image]], [[None, "achernar"]], "Guardião calmo"]], thumb, [1024, 1024]]
        payload = [None, [], [], [], None, [row], None, None]
        chars = parse_characters(payload, project)
        self.assertEqual(len(chars), 1)
        self.assertEqual(chars[0], {
            "entity_id": entity,
            "project_id": project,
            "display_name": "Lake keeper",
            "reference_media_ids": [image],
            "portrait_media_id": image,
            "body_media_id": None,
            "voice": "achernar",
            "personality": "Guardião calmo",
            "thumbnail_media_id": thumb,
        })

    def test_parse_characters_keeps_slot_positions_with_empty_portrait(self):
        from flow_character import parse_characters
        project, entity, body = str(uuid4()), str(uuid4()), str(uuid4())
        row = [project, entity, None, [1, "Kai", [[[], [body]]]], None, None]
        char = parse_characters([None, [], [], [], None, [row], None, None], project)[0]
        self.assertEqual((char["portrait_media_id"], char["body_media_id"], char["reference_media_ids"]),
                         (None, body, [body]))

    async def test_set_image_clears_occupied_slot_before_adding_and_never_resends(self):
        project, entity, old_body, old_portrait, copy, new = (str(uuid4()) for _ in range(6))
        def payload(images):
            row = [project, entity, None, [1, "Kai", [images]], None, None]
            return [None, [], [], [], None, [row], None, None]
        assets = [{"media_id": new, "workflow_id": str(uuid4()), "kind": "image"}]
        with patch("asyncio.sleep", AsyncMock()), patch("flow_assets.parse_assets", return_value=assets):
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
                payload([[old_portrait], [old_body]]), {},
                payload([[old_portrait], []]), {},
                payload([[old_portrait], [copy]]),
            ]))
            result = await manage_character("conta-a", project, "set_image", entity_id=entity,
                                            image_media_id=new, slot="body", client=client)
            self.assertEqual(result["status"], "image_set")
            calls = [(c.args[0], c.kwargs.get("params")) for c in client.rpc.await_args_list]
            clear = next(p for r, p in calls if r == "rzMKMb")
            self.assertEqual(clear, [[project, entity, None, [1, None, [[[old_portrait], []]]]],
                                     [["entity_info.character_info.image_references"]]])
            add = next(p for r, p in calls if r == "Sc7aEb")
            self.assertEqual(add[7], [None, None, [entity, [1]]])
            self.assertEqual([r for r, _ in calls].count("Sc7aEb"), 1)

            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
                payload([[old_portrait], [old_body]]), {},
                payload([[], [old_body]]), payload([[], [old_body]])]))
            result = await manage_character("conta-a", project, "remove_image", entity_id=entity,
                                            slot="portrait", client=client)
            self.assertEqual(result["status"], "image_removed")
            with self.assertRaises(ValueError):
                await manage_character("conta-a", project, "set_image", entity_id=entity,
                                       image_media_id=new, slot="side", client=client)

    async def test_set_image_by_description_generates_into_body_slot_once(self):
        project, entity, copy = (str(uuid4()) for _ in range(3))
        def payload(images):
            row = [project, entity, None, [1, "Kai", [images]], None, None]
            return [None, [], [], [], None, [row], None, None]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
            payload([[str(uuid4())]]), payload([[], [copy]])]))
        generate = AsyncMock(return_value={"status": "completed", "job_id": "j1"})
        with patch("asyncio.sleep", AsyncMock()), patch("flow_video.generate_images", generate):
            result = await manage_character("conta-a", project, "set_image", entity_id=entity,
                                            description="Corpo inteiro", max_credits=0, slot="body",
                                            client=client)
        self.assertEqual(result["status"], "image_set")
        generate.assert_awaited_once()
        self.assertEqual(generate.await_args.kwargs["character_slot"], 1)
        with self.assertRaises(ValueError):
            await manage_character("conta-a", project, "set_image", entity_id=entity, client=client)

    async def test_remove_image_when_slot_already_empty_fails_pre_submit(self):
        project, entity = str(uuid4()), str(uuid4())
        char_row = [project, entity, None, [1, "Kai", [[[], []]]], None, None]
        payload = [None, [], [], [], None, [char_row], None, None]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=payload))
        result = await manage_character("conta-a", project, "remove_image", entity_id=entity,
                                        slot="portrait", client=client)
        self.assertEqual(result["status"], "failed_pre_submit")
        self.assertEqual(result["error"], "O slot do personagem já está vazio.")
        self.assertFalse(result["retry_automatically"])
        # Chamou apenas a leitura inicial Zzl0ze, sem rpc de mutação
        self.assertEqual(len(client.rpc.await_args_list), 1)
        self.assertEqual(client.rpc.await_args_list[0].args[0], "Zzl0ze")


    async def test_set_image_invalid_slot_fails_before_rpc(self):
        project, entity, image = str(uuid4()), str(uuid4()), str(uuid4())
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock())
        with self.assertRaises(ValueError) as ctx:
            await manage_character("conta-a", project, "set_image", entity_id=entity,
                                   image_media_id=image, slot="side", client=client)
        self.assertIn("slot deve ser portrait ou body", str(ctx.exception))
        client.rpc.assert_not_awaited()


if __name__ == "__main__":

    unittest.main()

