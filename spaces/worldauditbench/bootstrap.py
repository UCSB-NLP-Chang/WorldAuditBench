"""Restore a pinned asset archive, then serve the Space on its single public port."""
import hashlib,json,os,tarfile
from pathlib import Path
from huggingface_hub import hf_hub_download

ROOT=Path(__file__).resolve().parent

def restore():
    existing=os.environ.get('WAB_RUNTIME_CONFIG')
    if existing and Path(existing).is_file():return
    metadata=json.loads((ROOT/'assets.json').read_text())
    repo=os.environ.get('WAB_ASSET_REPO') or metadata.get('repo')
    bundled=ROOT/'indoor-demo.tar.gz'
    if repo:
        revision=os.environ.get('WAB_ASSET_REVISION') or metadata['revision']
        expected=os.environ.get('WAB_ARCHIVE_SHA256') or metadata['sha256']
        if len(revision)!=40:raise ValueError('Asset revision must be pinned')
        path=hf_hub_download(repo_id=repo,repo_type='dataset',revision=revision,
            filename=os.environ.get('WAB_ASSET_FILE','indoor-demo.tar.gz'),token=os.environ.get('HF_TOKEN'))
    elif bundled.is_file():
        path=bundled
        expected=json.loads((ROOT/'assets.json').read_text())['sha256']
    else:return
    if len(expected)!=64:raise ValueError('Asset SHA-256 must be pinned')
    with open(path,'rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    if digest!=expected:raise ValueError('Asset archive hash mismatch')
    folder=Path(os.environ.get('WAB_ASSET_DIR','/tmp/worldauditbench-assets')).resolve();folder.mkdir(parents=True,exist_ok=True)
    with tarfile.open(path) as archive:archive.extractall(folder,filter='data')
    release=json.loads((folder/'release.json').read_text())
    binary=(folder/release['binary']).resolve()
    policy=(folder/release['policy']).resolve()
    if not binary.is_relative_to(folder) or not policy.is_relative_to(folder):raise ValueError('Invalid release paths')
    binary.chmod(binary.stat().st_mode | 0o100)
    config={'binary':str(binary),'sha256':release['sha256'],'policy':str(policy)}
    target=folder/'runtime.json';target.write_text(json.dumps(config))
    os.environ['WAB_RUNTIME_CONFIG']=str(target)

if __name__=='__main__':
    try:restore()
    except Exception as e:print('Asset restore failed:',type(e).__name__,flush=True)
    os.execvp('uvicorn',['uvicorn','app:app','--host','0.0.0.0','--port','7860','--no-access-log'])
