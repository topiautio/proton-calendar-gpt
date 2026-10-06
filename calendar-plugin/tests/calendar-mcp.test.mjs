import test from 'node:test';
import assert from 'node:assert/strict';
import { handleMcp, handleConnectionHealth } from '../lib/calendar-mcp.ts';
const env = { PROTON_ADAPTER_URL: 'https://calendar.test', PROTON_ACTION_API_KEY: 'a'.repeat(40) };
const request = (method, params, auth=true) => new Request('https://plugin.test/mcp', { method: 'POST', headers: { 'content-type': 'application/json', ...(auth ? { 'oai-authenticated-user-id': 'test-owner' } : {}) }, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }) });
const call = async (name, args={}, config=env) => (await handleMcp(request('tools/call', { name, arguments: args }), config)).json();

test('hosting health diagnostic sends no credentials and never returns upstream data', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'https://calendar.test/healthz');
    assert.equal(options.headers, undefined);
    return Response.json({status:'ok', private_data:'must not be returned'});
  };
  try {
    const response = await handleConnectionHealth(new Request('https://plugin.test/connection-health'), env);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const result = await response.json();
    assert.equal(result.reachable, true);
    assert.ok(result.checked_at);
    assert.doesNotMatch(JSON.stringify(result), /private_data|must not be returned/);
    globalThis.fetch = async () => { throw new Error('DNS resolution failed'); };
    const failed = await (await handleConnectionHealth(new Request('https://plugin.test/connection-health'), env)).json();
    assert.equal(failed.network_error, 'dns');
    assert.doesNotMatch(JSON.stringify(failed), /secret upstream text/);
  } finally { globalThis.fetch = original; }
});

test('anonymous requests never reach the calendar; initialization and discovery work', async () => {
  assert.equal((await handleMcp(request('tools/list', {}, false), env)).status, 401);
  const init = await (await handleMcp(request('initialize', { protocolVersion: '2025-06-18' }), env)).json();
  assert.equal(init.result.protocolVersion, '2025-06-18');
  const list = await (await handleMcp(request('tools/list'), env)).json();
  assert.deepEqual(list.result.tools.map(t=>t.name), ['getIntegrationStatus','getCalendarContext','createCalendarEvent','getEventStatus']);
});

test('undeployed calendar reports disconnected and cannot pretend to save an event', async () => {
  const status = await call('getIntegrationStatus', {}, {});
  assert.equal(status.result.structuredContent.configured, false);
  const write = await call('createCalendarEvent', { title: 'School', start: '2026-10-07T09:45:00+03:00' }, {});
  assert.equal(write.result.isError, true);
});

test('invalid event, job IDs and unexpected arguments never go upstream', async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error('should never fetch'); };
  try {
    for (const [name, args] of [['getEventStatus',{job_id:'../context'}],['getCalendarContext',{extra:true}],['createCalendarEvent',{title:'Test',start:'2026-10-07T09:45:00'}],['createCalendarEvent',{title:'Test',start:'2026-10-07T09:45:00Z',guests:['x']}]]) {
      assert.equal((await call(name,args)).result.isError, true);
    }
    assert.equal(calls, 0);
  } finally { globalThis.fetch = original; }
});

test('write forwards only the validated event and polling preserves the same job', async () => {
  const original = globalThis.fetch; const requests = []; const id = 'b'.repeat(64);
  const payload = {title:'School', start:'2026-10-07T09:45:00+03:00'};
  globalThis.fetch = async (url, options) => {
    requests.push({url,options});
    return Response.json({job_id:id,state:'pending',event:payload,error:'',calendar_url:'https://calendar.proton.me',poll_after_seconds:3});
  };
  try {
    const result = await call('createCalendarEvent', payload);
    assert.equal(result.result.structuredContent.state,'pending');
    assert.deepEqual(JSON.parse(requests[0].options.body),payload);
    assert.equal(requests[0].options.redirect,'manual');
    assert.equal(requests[0].options.headers.Authorization,`Bearer ${env.PROTON_ACTION_API_KEY}`);
    await call('getEventStatus',{job_id:id});
    assert.equal(requests[1].url,`https://calendar.test/events/${id}`);
    assert.equal(requests[1].options.method,'GET');
  } finally { globalThis.fetch = original; }
});

test('redirects fail without forwarding the API key to another destination', async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async (url, options) => {
    calls++;
    assert.equal(url, 'https://calendar.test/context');
    assert.equal(options.redirect, 'manual');
    return new Response(null, {status:302,headers:{Location:'https://other.test/context'}});
  };
  try {
    const status = await call('getIntegrationStatus');
    assert.equal(status.result.structuredContent.reachable, false);
    assert.ok(status.result.structuredContent.checked_at);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

test('uncertain writes and upstream secrets are never exposed or retried', async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error('secret token password'); };
  try {
    const result = await call('createCalendarEvent',{title:'Test',start:'2026-10-07T09:45:00Z'});
    assert.equal(result.result.isError,true);
    assert.match(result.result.content[0].text,/may have been accepted/);
    assert.doesNotMatch(JSON.stringify(result),/secret token password/);
    assert.equal(calls,1);
    globalThis.fetch = async () => new Response('upstream secret', {status:401});
    assert.doesNotMatch(JSON.stringify(await call('getCalendarContext')),/upstream secret/);
  } finally { globalThis.fetch = original; }
});
