# =====================================================================================
# STEP RB-002.1 - Confirm the local lab can be started safely                  [~30 sec]
#
# Goal / What: Confirm Docker Engine and Docker Compose are reachable, the lab files
#              are present, and the disposable container name is not already in use.
# Why: A clean preflight prevents us from overwriting an older exercise and records the
#      Docker versions before we rely on version-specific health-check behavior.
# Where / How: [LAPTOP - PowerShell 5.1+] Start in the argus\runbooks directory and
#              paste this entire block into PowerShell.
# READ-ONLY: Reads local files and Docker metadata. It creates, starts, stops, or removes
#            nothing. Undo: none required.
# Expected: Version lines followed by exactly `RB002 PREFLIGHT OK`.
# If it fails: Stop and return the complete output. Do not remove an existing container.
# =====================================================================================

$ErrorActionPreference = "Stop"

try {
    $labPath = (Resolve-Path -LiteralPath ".\practice\RB-002").Path
    $requiredFiles = @("compose.yaml", "Dockerfile", "app.py")
    foreach ($requiredFile in $requiredFiles) {
        $candidate = Join-Path $labPath $requiredFile
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Required lab file is missing: $candidate"
        }
    }

    $engineVersion = docker version --format '{{.Server.Version}}'
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($engineVersion)) {
        throw "Docker Engine is not reachable. Start Docker Desktop, then rerun this same step."
    }

    $composeVersion = docker compose version --short
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($composeVersion)) {
        throw "Docker Compose v2 is not available."
    }

    $existingContainer = docker ps -a --filter "name=^/argus-lab-rb002$" --format '{{.Names}}'
    if ($LASTEXITCODE -ne 0) {
        throw "Docker could not check for an existing lab container."
    }
    if (-not [string]::IsNullOrWhiteSpace($existingContainer)) {
        throw "Container argus-lab-rb002 already exists. Stop here so we can identify it safely."
    }

    Write-Output "LAB_PATH=$labPath"
    Write-Output "DOCKER_ENGINE_VERSION=$engineVersion"
    Write-Output "DOCKER_COMPOSE_VERSION=$composeVersion"
    Write-Output "RB002 PREFLIGHT OK"
}
catch {
    Write-Output "RB002 PREFLIGHT STOP: $($_.Exception.Message)"
    exit 1
}

# >>> Paste all terminal output into chat or practice/RB-002/output.bash and tell the
#     agent `output.bash updated`. Do not continue to another command yet. <<<
