import assert from 'node:assert/strict';
import test from 'node:test';

import { ChannelType, MessageFlags, PermissionFlagsBits, PermissionsBitField } from 'discord.js';

import { channelSummaryCommand, summarizeCurrentChannel } from '../src/channel_summary.js';

const config = { python: 'python', repoRoot: 'repo', botDb: 'messages.sqlite3' };

function createInteraction({ privateThread = false, userInThread = true } = {}) {
  const user = { id: 'user' };
  const bot = { id: 'bot' };
  const allowed = new PermissionsBitField([PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory]);
  let userPermissions = allowed;
  const replies = [];
  const channel = {
    id: '123',
    parentId: 'parent',
    type: privateThread ? ChannelType.PrivateThread : ChannelType.GuildText,
    isThread: () => privateThread,
    isTextBased: () => true,
    messages: {},
    permissionsFor: (member) => (member === user ? userPermissions : allowed),
    members: {
      cache: new Map([[user.id, user]]),
      fetch: async ({ member }) => {
        if (member === bot.id || userInThread) return member;
        throw new Error('Cannot verify thread membership');
      },
    },
  };
  const interaction = {
    guildId: '456',
    channelId: channel.id,
    user,
    client: { user: bot },
    guild: {
      channels: { fetch: async (id) => (id === channel.id ? channel : { id }) },
      members: { fetch: async ({ user: id }) => (id === user.id ? user : bot) },
    },
    deferReply: async (options) => {
      assert.equal(options.flags, MessageFlags.Ephemeral);
    },
    editReply: async (reply) => replies.push(reply),
  };
  return {
    interaction,
    replies,
    revokeHistory: () => {
      userPermissions = new PermissionsBitField([PermissionFlagsBits.ViewChannel]);
    },
  };
}

test('channel summary privately replies with the current guild and channel only', async () => {
  const { interaction, replies } = createInteraction();
  assert.equal(channelSummaryCommand.toJSON().name, 'summary_this_channel');
  await summarizeCurrentChannel(interaction, config, async (input) => {
    assert.deepEqual(input, { ...config, guildId: interaction.guildId, channelId: interaction.channelId });
    return { count: 2, summary: '專題進度摘要' };
  });
  assert.match(replies[0].content, /2 則已記錄文字.*專題進度摘要/s);
  assert.deepEqual(replies[0].allowedMentions.parse, []);
});

test('channel summary blocks missing history permission and unverifiable private thread membership', async () => {
  const noHistory = createInteraction();
  noHistory.revokeHistory();
  for (const { interaction, replies } of [noHistory, createInteraction({ privateThread: true, userInThread: false })]) {
    let summaryCalls = 0;
    await summarizeCurrentChannel(interaction, config, async () => {
      summaryCalls++;
      return { count: 1, summary: 'private' };
    });
    assert.equal(summaryCalls, 0);
    assert.match(replies[0], /無法確認/);
  }
});

test('channel summary is withheld when permission is revoked during summarization', async () => {
  const { interaction, replies, revokeHistory } = createInteraction();
  await summarizeCurrentChannel(interaction, config, async () => {
    revokeHistory();
    return { count: 1, summary: 'private' };
  });
  assert.match(replies[0], /無法確認/);
});
