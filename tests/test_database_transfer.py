import pytest
from incident_room.storage import Store
from incident_room.auth import AuthStore
from incident_room.database_transfer import export_database,import_database

def test_history_and_identity_transfer_is_exact_and_refuses_overwrite(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTH_MEMBERS','{}')
    source='sqlite:///'+(tmp_path/'source.db').as_posix()
    target='sqlite:///'+(tmp_path/'target.db').as_posix()
    store=Store(source);auth=AuthStore(store)
    auth.set_member('finance@gmail.com','finance')
    auth.challenge()
    doc=store.save({'id':'incident-1','stage':'OPEN','version':0,'evidence':[]},0,{'type':'opened','actor':'Finance','actor_id':'google:stable-id'})
    path=tmp_path/'transfer.json'
    counts=export_database(source,path)
    assert 'auth_sessions' not in path.read_text() and 'auth_challenges' not in path.read_text()
    assert import_database(target,path)==counts
    copied=Store(target)
    assert copied.get('incident-1')==doc
    assert copied.history('incident-1')==store.history('incident-1')
    assert AuthStore(copied).member('finance@gmail.com')['role']=='finance'
    with pytest.raises(ValueError,match='empty'):import_database(target,path)
    assert copied.get('incident-1')==doc
