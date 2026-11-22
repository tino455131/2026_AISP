import assert from 'node:assert/strict';
import test from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';

import { MessageFlags, SlashCommandBuilder } from 'discord.js';
import { aiCommand } from '../src/ai.js';
import { channelAskCommand, askCurrentChannel } from '../src/channel_ask.js';
import { channelSummaryCommand } from '../src/channel_summary.js';
import { recordCommand } from '../src/commands.js';
import { helpCommand, showHelp } from '../src/help.js';
import { meetingCommand } from '../src/meetings.js';

const config = { readerPython: 'reader', repoRoot: 'root', botDb: 'db' };

function interactionFor(question = '解釋 async') {
  const replies = [];
  const interaction = {
    guildId: '10', channelId: '20', user: { id: '30' },
    options: { getString: () => question },
    deferReply: async ({ flags }) => assert.equal(flags, MessageFlags.Ephemeral),
    editReply: async (value) => replies.push(value),
  };
  return { interaction, replies };
}

test('/help is private and describes every registered command and subcommand', async () => {
  const ping = new SlashCommandBuilder().setName('ping').setDescription('確認 bot 在線上');
  const definitions = [recordCommand, meetingCommand, aiCommand, channelSummaryCommand, channelAskCommand, ping, helpCommand]
    .map((command) => command.toJSON());
  const interaction = {
    reply: async ({ flags, content }) => {
      assert.equal(flags, MessageFlags.Ephemeral);
      for (const { name, description, options } of definitions) {
        assert.ok(content.includes('/' + name));
        assert.ok(content.includes(description));
        for (const option of options ?? []) {
          if (option.type === 1) assert.ok(content.includes('/' + name + ' ' + option.name));
        }
      }
    },
  };
  await showHelp(interaction, definitions);
  const askOption = channelAskCommand.toJSON().options[0];
  assert.equal(askOption.required, true);
  assert.equal(askOption.max_length, 1000);
});

test('/ask uses trusted interaction IDs and general answers do not need history permission', async () => {
  const { interaction, replies } = interactionFor();
  await askCurrentChannel(interaction, config, async (input) => {
    assert.equal(input.python, 'reader');
    assert.deepEqual(input.request, { question: '解釋 async', guild_id: '10', channel_id: '20', member_id: '30' });
    return { ok: true, used_channel_history: false, text: '非同步函式' };
  }, { access: async () => assert.fail('General answers do not need a history check') });
  assert.deepEqual(replies, [{ content: '非同步函式', allowedMentions: { parse: [] } }]);
});

test('/ask withholds a historical answer if access is revoked or unverified', async () => {
  const { interaction, replies } = interactionFor('我們剛才決定了什麼？');
  for (const access of [async () => null, async () => { throw new Error('Discord unavailable'); }]) {
    await askCurrentChannel(interaction, config, async () => ({
      ok: true, used_channel_history: true, text: 'private history',
    }), { access });
  }
  assert.equal(replies.length, 2);
  for (const reply of replies) assert.match(reply, /暫時無法確認/);
});

test('/ask attaches long authorized answers and aborts overdue requests', async () => {
  const { interaction, replies } = interactionFor();
  await askCurrentChannel(interaction, config, async () => ({
    ok: true, used_channel_history: true, text: '長'.repeat(2001),
  }), { access: async () => ({ id: '20' }) });
  assert.equal(replies[0].files[0].name, 'ai-answer.md');

  let signal;
  await askCurrentChannel(interaction, config, async (input) => {
    signal = input.signal;
    await delay(100, undefined, { signal });
  }, { timeoutMs: 5 });
  assert.equal(signal.aborted, true);
  assert.match(replies[1], /逾時/);
});
