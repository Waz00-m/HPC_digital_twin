#Requires -Version 5.1
<#
.SYNOPSIS
Imports asserted Warehouse and SmartBin records from the starter RDF/XML ontology into Ditto.
.DESCRIPTION
Reads the local OWL file, validates all records, then creates Things or merges only
the mapped attributes into existing Things. Existing policies and features are kept.
This is a mapper for the starter schema, not a general OWL importer or reasoner.
.EXAMPLE
.\Import-SmartBinOntology.ps1 -Preview
.EXAMPLE
.\Import-SmartBinOntology.ps1
#>
[CmdletBinding()]
param(
    [string]$OntologyPath,
    [string]$DittoUrl = 'http://localhost:8090',
    [ValidatePattern('^[A-Za-z0-9_.-]+$')]
    [string]$Namespace = 'smartbin',
    [System.Management.Automation.PSCredential]$Credential,
    [switch]$Preview
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$rdfNamespace = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
$owlNamespace = 'http://www.w3.org/2002/07/owl#'
$xmlNamespace = 'http://www.w3.org/XML/1998/namespace'
if ([string]::IsNullOrWhiteSpace($OntologyPath)) {
    $scriptDirectory = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($scriptDirectory)) {
        $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $OntologyPath = Join-Path $scriptDirectory 'smartbin-demo.owl'
}

function Resolve-RdfIri([System.Xml.XmlElement]$Element, [string]$Value) {
    $baseUri = $sourceUri
    $ancestors = [System.Collections.Generic.List[System.Xml.XmlElement]]::new()
    $cursor = $Element
    while ($null -ne $cursor -and $cursor -is [System.Xml.XmlElement]) {
        $ancestors.Insert(0, $cursor)
        $cursor = $cursor.ParentNode
    }
    foreach ($ancestor in $ancestors) {
        if ($ancestor.HasAttribute('base', $xmlNamespace)) {
            $baseUri = [Uri]::new($baseUri, $ancestor.GetAttribute('base', $xmlNamespace))
        }
    }
    return [Uri]::new($baseUri, $Value).AbsoluteUri
}

function Get-SubjectIri([System.Xml.XmlElement]$Element) {
    if ($Element.HasAttribute('about', $rdfNamespace)) {
        return Resolve-RdfIri $Element $Element.GetAttribute('about', $rdfNamespace)
    }
    if ($Element.HasAttribute('ID', $rdfNamespace)) {
        return Resolve-RdfIri $Element ('#' + $Element.GetAttribute('ID', $rdfNamespace))
    }
    throw 'The starter importer requires named RDF resources (rdf:about or rdf:ID).'
}

function Get-LocalName([string]$Iri) {
    $splitAt = [Math]::Max($Iri.LastIndexOf('#'), $Iri.LastIndexOf('/'))
    return $Iri.Substring($splitAt + 1)
}

function Get-OneValue($Record, [string]$Property, [switch]$Resource, [switch]$Optional) {
    $values = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($element in $Record.Elements) {
        foreach ($child in $element.ChildNodes) {
            if ($child -isnot [System.Xml.XmlElement] -or
                $child.NamespaceURI -cne $schemaNamespace -or $child.LocalName -cne $Property) { continue }
            if ($Resource) {
                if (-not $child.HasAttribute('resource', $rdfNamespace)) {
                    throw "$($Record.Iri): $Property must reference a named individual using rdf:resource."
                }
                [void]$values.Add((Resolve-RdfIri $child $child.GetAttribute('resource', $rdfNamespace)))
            } else {
                if ($child.HasAttribute('resource', $rdfNamespace) -or @($child.SelectNodes('*')).Count -gt 0) {
                    throw "$($Record.Iri): $Property must be a plain typed literal."
                }
                [void]$values.Add($child.InnerText.Trim())
            }
        }
    }
    if ($Optional -and $values.Count -eq 0) { return $null }
    if ($values.Count -ne 1) {
        throw "$($Record.Iri): expected exactly one explicit $Property value; found $($values.Count)."
    }
    foreach ($value in $values) {
        if ([string]::IsNullOrWhiteSpace($value)) { throw "$($Record.Iri): $Property is empty." }
        return $value
    }
}

function Assert-Identifier([string]$Value) {
    if ($Value -cnotmatch '^[A-Za-z0-9_.-]+$') {
        throw "Unsupported identifier '$Value'. Use letters, digits, dots, underscores or hyphens."
    }
}

# Parse securely, without resolving external entities or downloading OWL imports.
$resolvedPath = (Resolve-Path -LiteralPath $OntologyPath).ProviderPath
$sourceUri = [Uri]::new($resolvedPath)
$settings = [System.Xml.XmlReaderSettings]::new()
$settings.DtdProcessing = [System.Xml.DtdProcessing]::Prohibit
$settings.XmlResolver = $null
$reader = [System.Xml.XmlReader]::Create($resolvedPath, $settings)
$model = [System.Xml.XmlDocument]::new()
$model.XmlResolver = $null
try { $model.Load($reader) } finally { $reader.Dispose() }
$ns = [System.Xml.XmlNamespaceManager]::new($model.NameTable)
$ns.AddNamespace('rdf', $rdfNamespace)
$ns.AddNamespace('owl', $owlNamespace)
if ($model.DocumentElement.NamespaceURI -cne $rdfNamespace -or $model.DocumentElement.LocalName -cne 'RDF') {
    throw 'Save the starter ontology as RDF/XML in Protege before importing.'
}
if (@($model.SelectNodes('//owl:imports', $ns)).Count -gt 0) {
    throw 'This mapper reads one self-contained RDF/XML file; external OWL imports are not followed.'
}
$ontologyNodes = @($model.SelectNodes('/rdf:RDF/owl:Ontology', $ns))
if ($ontologyNodes.Count -ne 1) { throw 'Expected one owl:Ontology declaration.' }
$ontologyIri = Get-SubjectIri $ontologyNodes[0]
$classIris = @{}
foreach ($classNode in $model.SelectNodes('/rdf:RDF/owl:Class', $ns)) {
    $classIri = Get-SubjectIri $classNode
    $className = Get-LocalName $classIri
    if ($className -cin @('Warehouse', 'SmartBin')) {
        if ($classIris.ContainsKey($className) -and $classIris[$className] -cne $classIri) {
            throw "Ambiguous $className declarations."
        }
        $classIris[$className] = $classIri
    }
}
if (-not $classIris.ContainsKey('Warehouse') -or -not $classIris.ContainsKey('SmartBin')) {
    throw 'The ontology must explicitly declare Warehouse and SmartBin classes from the starter schema.'
}
$schemaNamespace = $classIris['SmartBin'].Substring(0, $classIris['SmartBin'].Length - 'SmartBin'.Length)
if ($classIris['Warehouse'] -cne ($schemaNamespace + 'Warehouse')) {
    throw 'Warehouse and SmartBin must use the same starter schema namespace.'
}
$resources = [System.Collections.Generic.Dictionary[string, object]]::new([StringComparer]::Ordinal)
foreach ($element in $model.SelectNodes('/rdf:RDF/*[@rdf:about or @rdf:ID]', $ns)) {
    $iri = Get-SubjectIri $element
    if (-not $resources.ContainsKey($iri)) {
        $resources[$iri] = [pscustomobject]@{
            Iri = $iri
            Elements = [System.Collections.Generic.List[System.Xml.XmlElement]]::new()
            Types = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        }
    }
    $record = $resources[$iri]
    $record.Elements.Add($element)
    # Also support RDF/XML typed resource elements, as well as owl:NamedIndividual.
    [void]$record.Types.Add($element.NamespaceURI + $element.LocalName)
    foreach ($typeNode in $element.SelectNodes('rdf:type[@rdf:resource]', $ns)) {
        [void]$record.Types.Add((Resolve-RdfIri $typeNode $typeNode.GetAttribute('resource', $rdfNamespace)))
    }
}

$targets = [System.Collections.Generic.List[object]]::new()
$warehouseIds = [System.Collections.Generic.Dictionary[string, string]]::new([StringComparer]::Ordinal)
$thingIds = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($record in $resources.Values) {
    if ($record.Types.Contains($classIris['Warehouse'])) {
        if ($record.Types.Contains($classIris['SmartBin'])) { throw "$($record.Iri) is both a Warehouse and SmartBin." }
        $id = Get-OneValue $record 'warehouseId'
        Assert-Identifier $id
        $warehouseIds.Add($record.Iri, $id)
        $thingId = "${Namespace}:$id"
        if (-not $thingIds.Add($thingId)) { throw "Duplicate Thing ID: $thingId" }
        $targets.Add([pscustomobject]@{
            thingId = $thingId
            attributes = [ordered]@{
                type = 'Warehouse'; warehouseId = $id
                ontologyIri = $ontologyIri; ontologyIndividualIri = $record.Iri
                ontologyClassIri = $classIris['Warehouse']
            }
        })
    }
}
$warehouseCount = $targets.Count
foreach ($record in $resources.Values) {
    if (-not $record.Types.Contains($classIris['SmartBin'])) { continue }
    $id = Get-OneValue $record 'binId'
    Assert-Identifier $id
    $warehouseIri = Get-OneValue $record 'locatedIn' -Resource
    if (-not $warehouseIds.ContainsKey($warehouseIri)) {
        throw "$($record.Iri) refers to a warehouse that is not explicitly defined: $warehouseIri"
    }
    $capacityText = Get-OneValue $record 'capacityKg'
    $capacity = [decimal]0
    $numberStyle = [Globalization.NumberStyles]::AllowLeadingSign -bor [Globalization.NumberStyles]::AllowDecimalPoint
    if (-not [decimal]::TryParse($capacityText, $numberStyle, [Globalization.CultureInfo]::InvariantCulture, [ref]$capacity) -or $capacity -le 0) {
        throw "$($record.Iri): capacityKg must be a positive decimal number."
    }
    $thresholdText = Get-OneValue $record 'alertThresholdPercent' -Optional
    $threshold = $null
    if ($null -ne $thresholdText) {
        $parsedThreshold = [decimal]0
        if (-not [decimal]::TryParse($thresholdText, $numberStyle, [Globalization.CultureInfo]::InvariantCulture, [ref]$parsedThreshold) -or $parsedThreshold -le 0 -or $parsedThreshold -gt 100) {
            throw "$($record.Iri): alertThresholdPercent must be greater than 0 and at most 100."
        }
        $threshold = $parsedThreshold
    }
    $mqttTopic = Get-OneValue $record 'mqttTopic'
    if ($mqttTopic.Contains('+') -or $mqttTopic.Contains('#') -or $mqttTopic.Contains([char]0)) {
        throw "$($record.Iri): mqttTopic must be a concrete MQTT topic without wildcards or null characters."
    }
    $thingId = "${Namespace}:$id"
    if (-not $thingIds.Add($thingId)) { throw "Duplicate Thing ID: $thingId" }
    $targets.Add([pscustomobject]@{
        thingId = $thingId
        attributes = [ordered]@{
            type = 'SmartBin'; binId = $id; warehouseId = $warehouseIds[$warehouseIri]
            warehouseThingId = "${Namespace}:$($warehouseIds[$warehouseIri])"
            capacityKg = $capacity; mqttTopic = $mqttTopic; alertThresholdPercent = $threshold
            ontologyIri = $ontologyIri; ontologyIndividualIri = $record.Iri
            ontologyClassIri = $classIris['SmartBin']
        }
    })
}
$binCount = $targets.Count - $warehouseCount
if ($warehouseCount -eq 0 -or $binCount -eq 0) { throw 'No complete Warehouse/SmartBin fleet was found.' }
# Warehouses are created before bins which reference them.
$orderedTargets = @($targets | Sort-Object @{Expression = { if ($_.attributes.type -ceq 'Warehouse') { 0 } else { 1 } }}, thingId)
Write-Host "Validated $warehouseCount warehouses and $binCount bins from $resolvedPath"
if ($Preview) {
    $orderedTargets | ConvertTo-Json -Depth 8
    return
}

$serverUri = [Uri]$DittoUrl
if (-not $serverUri.IsAbsoluteUri -or $serverUri.Scheme -notin @('http', 'https') -or
    $serverUri.UserInfo -or $serverUri.Query -or $serverUri.Fragment -or $serverUri.AbsolutePath -ne '/') {
    throw 'DittoUrl must be a server origin such as http://localhost:8090, without credentials, a path, query or fragment.'
}
if ($serverUri.Scheme -eq 'http' -and -not $serverUri.IsLoopback) {
    throw 'Use HTTPS for a remote Ditto server. Plain HTTP is supported for local development only.'
}
if ($null -eq $Credential) {
    $Credential = Get-Credential -UserName 'ditto' -Message 'Enter your local Ditto username and password.'
    if ($null -eq $Credential) { throw 'Ditto credentials are required.' }
}
Add-Type -AssemblyName System.Net.Http
$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds(30)
$networkCredential = $Credential.GetNetworkCredential()
$authorization = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($networkCredential.UserName + ':' + $networkCredential.Password))
$client.DefaultRequestHeaders.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Basic', $authorization)
$apiOrigin = $serverUri.AbsoluteUri.TrimEnd('/')

function Invoke-DittoRequest([string]$Method, [string]$Path, $Body = $null, [hashtable]$Headers = @{}) {
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), $apiOrigin + '/api/2' + $Path)
    $response = $null
    try {
        foreach ($key in $Headers.Keys) { [void]$request.Headers.TryAddWithoutValidation($key, [string]$Headers[$key]) }
        if ($null -ne $Body) {
            $contentType = if ($Method -eq 'PATCH') { 'application/merge-patch+json' } else { 'application/json' }
            $request.Content = [System.Net.Http.StringContent]::new(($Body | ConvertTo-Json -Depth 12 -Compress), [Text.Encoding]::UTF8, $contentType)
        }
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $status = [int]$response.StatusCode
        if (-not $response.IsSuccessStatusCode -and -not ($Method -eq 'GET' -and $status -eq 404)) {
            throw "$Method $Path returned HTTP ${status}: $text"
        }
        $etag = if ($null -ne $response.Headers.ETag) { $response.Headers.ETag.ToString() -replace '^W/', '' } else { $null }
        $data = if ($text) { $text | ConvertFrom-Json } else { $null }
        return [pscustomobject]@{ Status = $status; Data = $data; ETag = $etag }
    } finally {
        if ($null -ne $response) { $response.Dispose() }
        $request.Dispose()
    }
}

try {
    $identity = Invoke-DittoRequest 'GET' '/whoami'
    if ($identity.Status -ne 200) { throw 'Cannot verify Ditto authentication.' }
    # Read every target before writing, so access errors do not cause a partial import.
    $plan = [System.Collections.Generic.List[object]]::new()
    foreach ($target in $orderedTargets) {
        $path = '/things/' + [Uri]::EscapeDataString($target.thingId)
        $existing = Invoke-DittoRequest 'GET' $path
        $changes = [ordered]@{}
        if ($existing.Status -eq 404) {
            $changes = $target.attributes
        } else {
            $attributeProperty = $existing.Data.PSObject.Properties['attributes']
            $currentAttributes = if ($null -ne $attributeProperty) { $attributeProperty.Value } else { $null }
            foreach ($key in $target.attributes.Keys) {
                $current = if ($null -ne $currentAttributes) { $currentAttributes.PSObject.Properties[$key] } else { $null }
                $expected = $target.attributes[$key]
                $same = $false
                if ($null -ne $current) {
                    if ($expected -is [decimal]) {
                        $same = $current.Value -is [ValueType] -and $current.Value -isnot [bool] -and [decimal]$current.Value -eq $expected
                    } else {
                        $same = $current.Value -is [string] -and $current.Value -ceq $expected
                    }
                }
                if (-not $same) { $changes[$key] = $expected }
            }
            if ($changes.Count -gt 0 -and -not $existing.ETag) { throw "Missing concurrency token for $($target.thingId); no import was started." }
        }
        $plan.Add([pscustomobject]@{ Target = $target; Path = $path; Existing = $existing; Changes = $changes })
    }
    $created = 0; $updated = 0; $unchanged = 0
    foreach ($step in $plan) {
        if ($step.Existing.Status -eq 404) {
            # With no policyId supplied, Ditto creates the default policy for this user.
            $null = Invoke-DittoRequest 'PUT' $step.Path @{ attributes = $step.Changes } @{ 'If-None-Match' = '*' }
            $created++
            Write-Host "Created   $($step.Target.thingId)"
        } elseif ($step.Changes.Count -gt 0) {
            # Merge only source-managed attributes. Never replace features or policyId.
            $null = Invoke-DittoRequest 'PATCH' $step.Path @{ attributes = $step.Changes } @{ 'If-Match' = $step.Existing.ETag }
            $updated++
            Write-Host "Updated   $($step.Target.thingId)"
        } else {
            $unchanged++
            Write-Host "Unchanged $($step.Target.thingId)"
        }
    }
    Write-Host "Import complete: $created created, $updated updated, $unchanged unchanged."
    [pscustomobject]@{ Created = $created; Updated = $updated; Unchanged = $unchanged; Warehouses = $warehouseCount; Bins = $binCount; DittoUrl = $apiOrigin }
} finally {
    $client.Dispose()
}
