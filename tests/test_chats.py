import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sara_app import chats,ai,storage

class ChatTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.patch=patch.object(chats,'FILE',Path(folder.name)/'chats.json');self.patch.start();self.addCleanup(self.patch.stop)
    def test_independent_chats_and_model_context(self):
        a=chats.create();b=chats.create()
        storage.append_conversation({'chat_id':a['id'],'question':'Private A','answer':'Answer A'})
        self.assertIn('Private A',ai.conversation_context(a['id']))
        with patch.object(ai,'CONVERSATION_HISTORY',[('user','Old global secret'),('assistant','answer')]):
            self.assertEqual(ai.conversation_context(b['id']),'')
        self.assertEqual(chats.messages(b['id']),[])
    def test_titles_and_delete_during_generation(self):
        a=chats.create();chats.append(a['id'],{'question':'Study physics','answer':'Okay'})
        self.assertEqual(chats.list_chats()[0]['title'],'Study physics')
        chats.rename(a['id'],'Physics exam');self.assertEqual(chats.list_chats()[0]['title'],'Physics exam')
        chats.delete(a['id']);self.assertFalse(chats.append(a['id'],{'answer':'late generation'}));self.assertEqual(chats.list_chats(),[])
    def test_retention_is_per_chat(self):
        a=chats.create();b=chats.create()
        chats.append(b['id'],{'answer':'keep me'})
        for n in range(202):chats.append(a['id'],{'question':str(n),'answer':'yes'})
        self.assertEqual(len(chats.messages(a['id'])),200)
        self.assertEqual(chats.messages(b['id'])[0]['answer'],'keep me')
    def test_invalid_titles_and_unknown_id(self):
        for title in ('',None,'x'*101):
            with self.assertRaises(ValueError):chats.create(title)
        with self.assertRaises(ValueError):chats.messages('../private')
