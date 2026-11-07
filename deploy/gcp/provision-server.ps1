param(
    [string]$ProjectId='incident-room-514005',
    [string]$Region='us-central1',
    [string]$Zone='us-central1-a'
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$record=Join-Path $projectRoot 'runtime\gcp-server.json'
$gcloud=(Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source
if (!$gcloud) {$gcloud=Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'}
if (!(Test-Path -LiteralPath $gcloud)) {throw 'Google Cloud CLI not found'}
$marker='Incident Room managed deployment'
$network='incident-room-net';$subnet="incident-room-$Region";$server='incident-room-server';$addressName='incident-room-ip'
$runtimeAccount="incident-room-runtime@$ProjectId.iam.gserviceaccount.com"
$state=[ordered]@{project=$ProjectId;region=$Region;zone=$Zone;server=$server;network=$network;subnet=$subnet;service_account=$runtimeAccount;created_at=(Get-Date).ToUniversalTime().ToString('o');completed_steps=@()}
New-Item -ItemType Directory -Path (Split-Path -Parent $record) -Force | Out-Null
function Save-Step([string]$Step) {
    $state.completed_steps+=@($Step)
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $record -Encoding UTF8
}
function Invoke-Cloud([string[]]$CloudArgs) {
    & $gcloud @CloudArgs --project=$ProjectId --quiet
    if ($LASTEXITCODE -ne 0) {throw ('Google Cloud operation failed: '+($CloudArgs[0..([Math]::Min(2,$CloudArgs.Count-1))] -join ' '))}
}
function Read-Cloud([string[]]$CloudArgs) {
    $response=& $gcloud @CloudArgs --project=$ProjectId --format=json
    if ($LASTEXITCODE -ne 0) {throw 'Could not verify the Google Cloud resource'}
    return ($response | ConvertFrom-Json)
}
$billing=Read-Cloud @('billing','projects','describe',$ProjectId)
if (!$billing.billingEnabled) {throw 'Project billing must be active before provisioning'}
$operatorEmail=(& $gcloud auth list --filter='status:ACTIVE' --format='value(account)').Trim()
if ($LASTEXITCODE -ne 0 -or !$operatorEmail -or $operatorEmail.Contains("`n")) {throw 'Exactly one active operator identity is required'}
$state.operator=$operatorEmail
Invoke-Cloud @('services','enable','iap.googleapis.com','oslogin.googleapis.com')
Save-Step 'administrative-apis-enabled'
$accounts=@(Read-Cloud @('iam','service-accounts','list',"--filter=email=$runtimeAccount"))
if (!$accounts.Count) {Invoke-Cloud @('iam','service-accounts','create','incident-room-runtime','--display-name=Incident Room runtime')}
Save-Step 'dedicated-runtime-identity'
$networks=@(Read-Cloud @('compute','networks','list',"--filter=name=$network"))
if ($networks.Count -and $networks[0].description -ne $marker) {throw 'Network name belongs to an unrecognized deployment'}
if (!$networks.Count) {Invoke-Cloud @('compute','networks','create',$network,'--subnet-mode=custom',"--description=$marker")}
$subnets=@(Read-Cloud @('compute','networks','subnets','list',"--filter=name=$subnet"))
if ($subnets.Count -and ($subnets[0].ipCidrRange -ne '10.44.0.0/24' -or !$subnets[0].network.EndsWith('/'+$network))) {throw 'Subnet name belongs to an unrecognized network'}
if (!$subnets.Count) {Invoke-Cloud @('compute','networks','subnets','create',$subnet,"--network=$network","--region=$Region",'--range=10.44.0.0/24','--enable-private-ip-google-access',"--description=$marker")}
Save-Step 'isolated-network'
$firewalls=@(Read-Cloud @('compute','firewall-rules','list','--filter=name=incident-room-iap-ssh'))
if ($firewalls.Count -and $firewalls[0].description -ne $marker) {throw 'Firewall rule name belongs to an unrecognized deployment'}
if (!$firewalls.Count) {Invoke-Cloud @('compute','firewall-rules','create','incident-room-iap-ssh',"--network=$network",'--direction=INGRESS','--action=ALLOW','--rules=tcp:22','--source-ranges=35.235.240.0/20','--target-tags=incident-room-server',"--description=$marker")}
Save-Step 'iap-only-administrative-ingress'
foreach ($role in @('roles/iap.tunnelResourceAccessor','roles/compute.osAdminLogin')) {
    Invoke-Cloud @('projects','add-iam-policy-binding',$ProjectId,"--member=user:$operatorEmail","--role=$role",'--condition=None','--format=none')
}
Save-Step 'existing-operator-server-access'
$addresses=@(Read-Cloud @('compute','addresses','list',"--filter=name=$addressName"))
if ($addresses.Count -and $addresses[0].description -ne $marker) {throw 'Address name belongs to an unrecognized deployment'}
if (!$addresses.Count) {Invoke-Cloud @('compute','addresses','create',$addressName,"--region=$Region",'--network-tier=PREMIUM',"--description=$marker")}
$address=Read-Cloud @('compute','addresses','describe',$addressName,"--region=$Region")
$state.public_ip=$address.address
Save-Step 'stable-server-address'
$instances=@(Read-Cloud @('compute','instances','list',"--filter=name=$server"))
if ($instances.Count -and ($instances[0].labels.app -ne 'incident-room' -or !$instances[0].zone.EndsWith('/'+$Zone))) {throw 'Server name belongs to an unrecognized deployment'}
if (!$instances.Count) {
    $bootstrap=Join-Path $PSScriptRoot 'bootstrap-server.sh'
    Invoke-Cloud @('compute','instances','create',$server,"--zone=$Zone",'--machine-type=e2-medium','--image-family=debian-12','--image-project=debian-cloud','--boot-disk-size=30GB','--boot-disk-type=pd-standard','--no-boot-disk-auto-delete','--deletion-protection',"--subnet=$subnet",("--address="+$address.address),'--network-tier=PREMIUM',"--service-account=$runtimeAccount",'--scopes=cloud-platform','--tags=incident-room-server','--labels=app=incident-room,managed-by=incident-room','--metadata=enable-oslogin=TRUE,block-project-ssh-keys=TRUE',"--metadata-from-file=startup-script=$bootstrap",'--shielded-secure-boot','--shielded-vtpm','--shielded-integrity-monitoring',"--description=$marker")
}
$instance=Read-Cloud @('compute','instances','describe',$server,"--zone=$Zone")
$state.status=$instance.status
$state.instance_id=$instance.id
Save-Step 'server-created'
Write-Host "Server $server is $($instance.status). Bootstrap installation is verified separately."
Write-Host 'Deployment record: runtime\gcp-server.json'
