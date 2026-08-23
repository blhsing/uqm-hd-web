const releaseTag = 'assets-v0.1.0';
const releaseApi = `https://api.github.com/repos/blhsing/uqm-hd-web/releases/tags/${releaseTag}`;
const releaseBase = `https://github.com/blhsing/uqm-hd-web/releases/download/${releaseTag}`;
const packages = [
  {
    name: 'hires4x.zip',
    bytes: 369_756_672,
    sha256: '76af440bd845a63bd42b88913347374eb62c40c149d0bea37045a10bd0bd6618',
  },
  {
    name: '3dovoice.zip',
    bytes: 146_438_532,
    sha256: 'a14dc7d655297e1b6c6eedc2a4dee30a164646e6525e353bb7fdc5da75232b09',
  },
  {
    name: '3domusic.zip',
    bytes: 21_934_569,
    sha256: '7142332040c13a153856d22487aaf82e6b30fc4d22333bcf7607712843bca689',
  },
  {
    name: 'native1080-zh_TW.uqm',
    bytes: 189_687_374,
    sha256: 'f24d1f55e326fe20bb577c53eb12836ecff71af7a8b34ea2520537ec4ef1aef2',
  },
];

const requestHeaders = { 'User-Agent': 'uqm-hd-web-upstream-check/0.1' };
const metadataResponse = await fetch(releaseApi, { headers: requestHeaders });
if (!metadataResponse.ok) {
  throw new Error(`GitHub Release metadata returned HTTP ${metadataResponse.status}.`);
}
const metadata = await metadataResponse.json();

for (const item of packages) {
  const asset = metadata.assets?.find(candidate => candidate.name === item.name);
  if (!asset || asset.size !== item.bytes || asset.digest !== `sha256:${item.sha256}`) {
    throw new Error(`${item.name} no longer matches its pinned GitHub Release digest.`);
  }

  const response = await fetch(`${releaseBase}/${encodeURIComponent(item.name)}`, {
    redirect: 'follow',
    headers: { ...requestHeaders, Range: 'bytes=0-3' },
  });
  if (response.status !== 206) {
    throw new Error(`${item.name} returned HTTP ${response.status}, not 206.`);
  }
  const total = Number(/\/(\d+)$/.exec(response.headers.get('content-range') || '')?.[1]);
  const header = Buffer.from(await response.arrayBuffer());
  if (total !== item.bytes || header.length !== 4 || header.readUInt32LE(0) !== 0x04034b50) {
    throw new Error(`${item.name} no longer matches the pinned ZIP metadata.`);
  }
}

console.log('All four browser assets match their pinned GitHub Release digests and ZIP metadata.');
