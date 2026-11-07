"""Package source and the SQL Git bundle for this private server deployment."""
import json
import os
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parents[2]
private=root.parents[1]/'private/gcp'
excluded={'.venv','.git','node_modules','.next','runtime','__pycache__','.pytest_cache','.uv-cache'}
config=json.loads((private/'project.cloud.json').read_text())
is_presentation=any('.incident_room_presentation.' in table for table in config['tables'])
bundle=private/('presentation-warehouse.bundle' if is_presentation else 'retail-warehouse.bundle')
if not bundle.is_file():raise RuntimeError('Save the active SQL Git bundle before packaging this project')
with tarfile.open(private/'cloud-source.tar.gz','w:gz') as archive:
    for directory,folders,files in os.walk(root):
        folders[:]=[folder for folder in folders if folder not in excluded]
        for name in files:
            path=Path(directory)/name;relative=path.relative_to(root)
            if name.startswith('.env') and name!='.env.example':continue
            if name.endswith(('.local.json','.tsbuildinfo')) or name in {'project.container.json','next-env.d.ts'}:continue
            archive.add(path,arcname=relative.as_posix(),recursive=False)
    for path,name in [(private/'project.cloud.json','config/project.container.json'),(bundle,'migration/retail.bundle'),(private/'cloud-release.json','deploy/gcp/release.json'),(root.parents[1]/'deploy/switch/compose.yaml','switch/compose.yaml'),(root.parents[1]/'deploy/switch/SWITCH-LICENSE','switch/SWITCH-LICENSE'),(root/'deploy/gcp/switch.cloud.yaml','switch/cloud.yaml')]:archive.add(path,arcname=name,recursive=False)
print('Private cloud source package prepared without credentials or browser sessions.')
