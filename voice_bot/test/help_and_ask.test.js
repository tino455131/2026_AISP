import assert from 'node:assert/strict';
import test from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';

import { ApplicationCommandOptionType, MessageFlags } from 'discord.js';
import { askCurrentChannel } from '../src/channel_ask.js';
import { commands, dispatchSlash } from '../src/slash_commands.js';

const config = { readerPython: 'reader', repoRoot: 'root', botDb: 'db' };

function interactionFor({ question = '解釋 async', privateReply = null, commandName = 'ask' } = {}) {
  const events = [];
  const interaction = {
    commandName, guildId: '10', channelId: '20', user: { id: '30', username: 'tester' },
    options: { getString: () => question, getBoolean: () => privateReply },
    reply: async (value) => events.push(['reply', value]),
    deferReply: async (value) => events.push(['defer', value]),
    editReply: async (value) => events.push(['edit', value]),
    followUp: async (value) => events.push(['follow', value]),
    channel: { send: async () => assert.fail('use the original interaction, not a separate channel message') },
  };
  return { interaction, events };
}

const success = { ok: true, used_channel_history: false, text: '非同步函式' };
const history = { ok: true, used_channel_history: true, text: 'protected answer' };

test('help is always private without options and only ask accepts the private option', async () => {
  assert.deepEqual(commands.map(({ name }) => name), ['help', 'ask']);
  const [help, ask] = commands;
  assert.deepEqual(help.options, []);
  const option = ask.options.find(({ name }) => name === 'private');
  assert.equal(option.type, ApplicationCommandOptionType.Boolean);
  assert.equal(Boolean(option.required), false);

  const { interaction, events } = interactionFor({ commandName: 'help' });
  delete interaction.options;
  await dispatchSlash(interaction, config);
  assert.equal(events[0][1].flags, MessageFlags.Ephemeral);
  assert.match(events[0][1].content, /\x60\/help\x60/);
  assert.match(events[0][1].content, /\x60\/ask\x60/);
  assert.doesNotMatch(events[0][1].content, /\/private|\/meeting|\/record|\/ping/);
  for (const cmd of ['private', 'ping', 'record', 'meeting', 'ai', 'summary_this_channel']) {
    const stopped = interactionFor({ commandName: cmd });
    await dispatchSlash(stopped.interaction, config);
    assert.equal(stopped.events[0][1].flags, MessageFlags.Ephemeral);
    assert.match(stopped.events[0][1].content, /暫停/);
  }
});

test('public /ask uses trusted Discord identity and updates its original reply with question and answer', async () => {
  for (const privateReply of [null, false]) {
    const { interaction, events } = interactionFor({ privateReply });
    await askCurrentChannel(interaction, config, async (input) => {
      assert.equal(input.python, 'reader');
      assert.deepEqual(input.request, {
        question: '解釋 async', guild_id: '10', channel_id: '20', member_id: '30', username: 'tester',
      });
      return success;
    }, {
      access: async () => assert.fail('General answers do not need history access'),
      audience: async () => assert.fail('General answers do not need a history audience check'),
    });
    assert.deepEqual(events.map(([method]) => method), ['reply', 'edit']);
    assert.equal(events[0][1].flags, undefined);
    assert.match(events[1][1].content, /<@30>.*解釋 async.*非同步函式/s);
    assert.deepEqual(events[1][1].allowedMentions, { parse: [] });
  }
});

test('private:true never sends a public ask reply', async () => {
  const { interaction, events } = interactionFor({ privateReply: true });
  await askCurrentChannel(interaction, config, async () => success);
  assert.deepEqual(events.map(([method]) => method), ['defer', 'edit']);
  assert.equal(events[0][1].flags, MessageFlags.Ephemeral);
  assert.match(events[1][1].content, /非同步函式/);
});

test('history needs an authorized audience to be public, and requester access to be shared at all', async () => {
  const question = 'sensitive question';
  const permitted = interactionFor({ question });
  await askCurrentChannel(permitted.interaction, config, async () => history, {
    audience: async () => true, access: async () => ({ id: '20' }),
  });
  assert.deepEqual(permitted.events.map(([method]) => method), ['reply', 'edit']);
  assert.match(permitted.events[1][1].content, /sensitive question.*protected answer/s);

  for (const audience of [async () => false, async () => { throw new Error('Discord unavailable'); }]) {
    const restricted = interactionFor({ question });
    await askCurrentChannel(restricted.interaction, config, async () => history, {
      audience, access: async () => ({ id: '20' }),
    });
    assert.deepEqual(restricted.events.map(([method]) => method), ['reply', 'follow', 'edit']);
    assert.equal(restricted.events[1][1].flags, MessageFlags.Ephemeral);
    assert.match(restricted.events[1][1].content, /sensitive question.*protected answer/s);
    for (const index of [0, 2]) assert.doesNotMatch(restricted.events[index][1].content, /sensitive|protected/);
  }

  const revoked = interactionFor({ question });
  await askCurrentChannel(revoked.interaction, config, async () => history, {
    audience: async () => true, access: async () => null,
  });
  assert.deepEqual(revoked.events.map(([method]) => method), ['reply', 'edit']);
  assert.match(revoked.events[1][1], /無法確認/);
});

test('/ask keeps a full long question in the reply and attaches its long answer', async () => {
  const question = String.fromCharCode(96).repeat(999) + '末';
  const { interaction, events } = interactionFor({ question });
  await askCurrentChannel(interaction, config, async () => ({ ...success, text: '長'.repeat(2001) }));
  const payload = events[1][1];
  assert.equal(payload.files[0].name, 'ai-answer.md');
  assert.ok(payload.content.length <= 2000);
  const displayed = payload.content.split(String.fromCharCode(96).repeat(3))[1].trim().replaceAll('\u200b', '');
  assert.equal(displayed, question);
});

test('/ask aborts overdue AI requests', async () => {
  const { interaction, events } = interactionFor();
  let signal;
  await askCurrentChannel(interaction, config, async (input) => {
    signal = input.signal;
    await delay(100, undefined, { signal });
  }, { timeoutMs: 5 });
  assert.equal(signal.aborted, true);
  assert.match(events[1][1], /逾時/);
});
