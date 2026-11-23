import assert from 'node:assert/strict';
import test from 'node:test';

import { ChannelType, PermissionFlagsBits as Permission, PermissionsBitField } from 'discord.js';
import { audienceCanRead, deliverResult } from '../src/replies.js';

function makeAudience({ canRead = true, privateThread = false, fail = false } = {}) {
  const publicMessages = [];
  const privateMessages = [];
  const allowed = new PermissionsBitField([Permission.ViewChannel, Permission.ReadMessageHistory]);
  const cannotRead = new PermissionsBitField([Permission.ViewChannel]);
  const channel = {
    id: '20', parentId: '10',
    type: privateThread ? ChannelType.PrivateThread : ChannelType.GuildText,
    isThread: () => privateThread,
    permissionsFor: ({ id }) => id === '2' && !canRead ? cannotRead : allowed,
    members: { fetch: async () => new Map([['1', { id: '1' }]]) },
    send: async (payload) => publicMessages.push(payload),
  };
  const interaction = {
    guild: {
      channels: { fetch: async () => channel },
      members: { list: async () => {
        if (fail) throw new Error('Discord unavailable');
        return new Map([['1', { id: '1' }], ['2', { id: '2' }]]);
      } },
      roles: { fetch: async () => {} },
    },
    channel,
    channelId: '20',
    user: { id: '1' },
    editReply: async (payload) => privateMessages.push(payload),
    deleteReply: async () => {},
  };
  return { interaction, publicMessages, privateMessages };
}

test('verified current-channel results are public, including attachments', async () => {
  const fixture = makeAudience();
  const result = { content: 'channel result', files: ['example.md'] };
  await deliverResult(fixture.interaction, result, { sourceChannelId: '20', verifyAccess: async () => true });
  assert.deepEqual(fixture.publicMessages, [{ ...result, allowedMentions: { parse: [] } }]);
  assert.deepEqual(fixture.privateMessages, []);
});

test('private threads consider membership, and protected result delivery fails closed', async () => {
  const thread = makeAudience({ canRead: false, privateThread: true });
  assert.equal(await audienceCanRead(thread.interaction), true);
  const cases = [
    [makeAudience({ canRead: false }), { sourceChannelId: '20' }],
    [makeAudience({ fail: true }), { sourceChannelId: '20' }],
    [makeAudience(), { sourceChannelId: 'another' }],
    [makeAudience(), { sourceChannelId: '20', privateReply: true }],
  ];
  for (const [fixture, policy] of cases) {
    const result = { content: 'private history' };
    await deliverResult(fixture.interaction, result, { ...policy, verifyAccess: async () => true });
    assert.deepEqual(fixture.publicMessages, []);
    assert.deepEqual(fixture.privateMessages, [result]);
  }
  const revoked = makeAudience();
  await deliverResult(revoked.interaction, { content: 'sensitive' }, {
    sourceChannelId: '20', verifyAccess: async () => false,
  });
  assert.deepEqual(revoked.publicMessages, []);
  assert.match(revoked.privateMessages[0], /無法確認/);
});
