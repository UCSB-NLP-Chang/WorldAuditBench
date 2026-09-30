import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
runtime=module('runtime_linux_test',ROOT/'runtime/mac_supervisor.py');server=module('server_linux_test',ROOT/'server.py')
class LinuxRuntimeTests(unittest.TestCase):
 def test_migration_manifest_rejects_other_task_and_command_suffix(self):
  with tempfile.TemporaryDirectory() as d:
   task={'id':'U018','revision':2,'sha256':'a'*64,'map':'/Game/Auditor/Migration/UE561/U018/R02/TaskMap_Candidate01'}
   s=server.Store(pathlib.Path(d)/'ok.db',{'tasks':[task]});s.db.close()
   for i,bad in enumerate([task['map'].replace('U018','U019'),task['map']+' -ExecCmds=quit',task['map'].replace('R02','R03')]):
    with self.assertRaises(ValueError):server.Store(pathlib.Path(d)/f'bad{i}.db',{'tasks':[{**task,'map':bad}]})
 def test_linux_launch_options_and_mac_defaults(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);manifest=root/'tasks.json';manifest.write_text(json.dumps({'tasks':[{'map':'/Game/Test'}]}))
   base={'manifest':str(manifest),'state_dir':d,'streamer_port':18882,'player_port':18082,'sfu_port':18892,'http_root':d,'signal_argv':['node','signal.js'],'signal_cwd':d,'binary':'/tmp/game'}
   for linux in (False,True):
    extra={'game_args':['-vulkan','-sm6'],'game_env':{'LD_LIBRARY_PATH':'/private/nvenc'},'peer_options':{'iceServers':[{'urls':['turn:127.0.0.1:23478?transport=tcp']}]}} if linux else {}
    supervisor=runtime.Supervisor({**base,**extra});sid=('b' if linux else 'a')*32
    with patch.object(supervisor,'spawn') as spawn:
     supervisor.run({'operation':'start','session_id':sid,'map':'/Game/Test','slot':0})
    game=spawn.call_args_list[1].args
    self.assertEqual(game[-1],extra.get('game_env'))
    self.assertEqual('-vulkan' in game[1],linux)
    config=json.loads((root/sid/'signal-config.json').read_text());self.assertEqual(config['peer_options'],extra.get('peer_options',{'iceServers':[]}))
if __name__=='__main__':unittest.main()
