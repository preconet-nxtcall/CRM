$ErrorActionPreference = "Stop"

$ServerIP = "165.22.215.145"
$User = "root"
$RemotePath = Read-Host "Enter remote path (default: /root/call-manager-pro)"
if ([string]::IsNullOrWhiteSpace($RemotePath)) {
    $RemotePath = "/root/call-manager-pro"
}

$ZipFile = "deploy_package.zip"

# Remove existing zip if it exists
if (Test-Path $ZipFile) {
    Remove-Item $ZipFile -Force
}

Write-Host "📦 Zipping files..."
# Exclude venv, __pycache__, .git, node_modules and the zip file itself
Get-ChildItem -Path . -Exclude $ZipFile, "venv", "__pycache__", ".git", "node_modules" | Compress-Archive -DestinationPath $ZipFile -Force -CompressionLevel Optimal

Write-Host "🚀 Uploading to $User@${ServerIP}:$RemotePath..."
try {
    scp $ZipFile "$User@${ServerIP}:$RemotePath/$ZipFile"
    if ($LASTEXITCODE -ne 0) { throw "SCP failed" }
} catch {
    Write-Error "❌ Upload failed. Please check your password and try again."
    exit 1
}

Write-Host "🔧 Running remote commands..."
try {
    # Construct command as a single line to avoid CRLF issues
    $Cmd = "cd $RemotePath && " +
           "python3 -m zipfile -e $ZipFile . && " +
           "rm $ZipFile && " +
           "sed -i 's/\r$//' build.sh && " +
           "chmod +x build.sh && " +
           "./build.sh && " +
           "(systemctl restart call-manager || echo '⚠️ Service call-manager not found. You may need to start it manually: gunicorn -w 4 -b 0.0.0.0:8000 run:app')"

    ssh "$User@$ServerIP" $Cmd
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed" }
} catch {
    Write-Error "❌ Remote execution failed. Please check your password and try again."
    exit 1
}

Write-Host "✅ Deployment complete!"
if (Test-Path $ZipFile) {
    Remove-Item $ZipFile -Force
}
