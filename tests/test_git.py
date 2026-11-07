import subprocess
from types import SimpleNamespace as NS
from incident_room.project import Project


def test_exact_patch_branch_preserves_main_checkout(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    def git(*args):return subprocess.run(['git',*args],cwd=repo,check=True,capture_output=True,text=True).stdout.strip()
    git('init')
    git('config','user.name','Test Reviewer');git('config','user.email','test@example.invalid')
    original='SELECT amount FROM `project.dataset.orders`\n'
    (repo/'model.sql').write_text(original)
    git('add','.');git('commit','-m','Initial SQL')
    head=git('rev-parse','HEAD')
    project=Project();project.root=repo;project.config=NS(transforms=['model.sql'],publish_pr=False)
    work=tmp_path/'publish';work.mkdir()
    patch='SELECT amount / 100 AS amount FROM `project.dataset.orders`\n'
    result=project.publish('abc123',{'file':'model.sql','content':patch,'reason':'Evidence-backed fix','digest':'tested-digest'},work)
    assert git('show',result['commit']+':model.sql')==patch.strip()
    assert git('rev-parse','HEAD')==head and (repo/'model.sql').read_text()==original
    assert not git('status','--porcelain') and not result['deployed']
