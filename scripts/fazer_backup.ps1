<#
Espelha o projeto, inclusive os dados locais, em outra pasta deste computador.

O espelhamento vai em um so sentido: a pasta de destino fica igual a esta, e o que
existir so no destino e apagado. Nunca edite nada na pasta de backup.

Uso:
  powershell -ExecutionPolicy Bypass -File scripts/fazer_backup.ps1 -Destino "<pasta de backup>"
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Destino
)

$origem = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path.TrimEnd("\")
$alvo = [IO.Path]::GetFullPath($Destino).TrimEnd("\")

if ($alvo.StartsWith("$origem\", [StringComparison]::OrdinalIgnoreCase) -or
    $origem.StartsWith("$alvo\", [StringComparison]::OrdinalIgnoreCase) -or
    $alvo -ieq $origem) {
    Write-Error "O destino nao pode ser esta pasta, uma subpasta ou uma pasta acima dela."
    exit 1
}

# Protege contra apagar por engano uma pasta que nao seja um backup deste projeto.
if ((Test-Path -LiteralPath $alvo) -and
    (Get-ChildItem -LiteralPath $alvo -Force | Select-Object -First 1) -and
    -not (Test-Path -LiteralPath (Join-Path $alvo "pyproject.toml"))) {
    Write-Error "O destino existe e nao parece ser um backup deste projeto: $alvo"
    exit 1
}

robocopy $origem $alvo /MIR /R:2 /W:2 /NFL /NDL /NJH /NP /XD .ipynb_checkpoints __pycache__ .pytest_cache

# No robocopy, codigos abaixo de 8 indicam sucesso.
if ($LASTEXITCODE -ge 8) {
    Write-Error "O backup falhou. Codigo do robocopy: $LASTEXITCODE"
    exit 1
}
Write-Output "Backup concluido em: $alvo"
exit 0
