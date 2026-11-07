// Minimal NEAR view access over plain JSON-RPC: no SDK, no key, no dependency.
// The dashboard uses the same calls from the browser (see ../web/index.html).

export const RPC = 'https://rpc.testnet.fastnear.com';

export async function rpc(method, params, url = RPC) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 'grip', method, params }),
  });
  const body = await res.json();
  if (body.error) {
    throw new Error(`${method}: ${body.error.message ?? JSON.stringify(body.error)}`);
  }
  return body.result;
}

/** Call a read-only contract method and return its decoded JSON value. */
export async function viewCall(contractId, methodName, args = {}, url = RPC) {
  // A view fired right after the transaction that wrote the state can land on a block that does not
  // have it yet, so retry briefly before giving up.
  let last;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const res = await rpc(
      'query',
      {
        request_type: 'call_function',
        finality: 'optimistic',
        account_id: contractId,
        method_name: methodName,
        args_base64: Buffer.from(JSON.stringify(args)).toString('base64'),
      },
      url,
    );
    if (res.logs?.length) {
      for (const line of res.logs) console.log(`  [contract] ${line}`);
    }
    if (res.result !== undefined) return JSON.parse(Buffer.from(res.result).toString('utf8'));
    last = res;
    await new Promise((r) => setTimeout(r, 1200));
  }
  throw new Error(`no result from ${methodName}: ${JSON.stringify(last).slice(0, 300)}`);
}

export async function viewAccount(accountId, url = RPC) {
  return rpc('query', { request_type: 'view_account', finality: 'optimistic', account_id: accountId }, url);
}
