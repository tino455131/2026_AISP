import { ChannelType, MessageFlags, PermissionFlagsBits as Permission } from 'discord.js';

export function replyFlags(privateReply) {
  return privateReply ? { flags: MessageFlags.Ephemeral } : {};
}

async function fetchSource(guild, channelId) {
  const channel = await guild.channels.fetch(channelId, { force: true });
  if (!channel?.permissionsFor) return null;
  if (channel.isThread() && !(await guild.channels.fetch(channel.parentId, { force: true }))) return null;
  return channel;
}

export async function readSourceAccess(guild, channelId, userId) {
  try {
    const [channel, member] = await Promise.all([
      fetchSource(guild, channelId), guild.members.fetch({ user: userId, force: true }),
    ]);
    const permissions = channel && member && channel.permissionsFor(member);
    if (!permissions) return { decision: 'unknown', channel, member };
    if (!permissions.has([Permission.ViewChannel, Permission.ReadMessageHistory])) return { decision: 'deny', channel, member };
    if (channel.type === ChannelType.PrivateThread && !permissions.has(Permission.ManageThreads)) {
      await channel.members.fetch({ member: userId, force: true, cache: false });
    }
    return { decision: 'allow', channel, member };
  } catch (error) {
    return { decision: [10007, 10003, 50001, 50013].includes(error.code) ? 'deny' : 'unknown', channel: null, member: null };
  }
}

async function* fetchPages(list, limit, signal) {
  let after;
  for (;;) {
    signal?.throwIfAborted();
    const page = await list({ after, limit, cache: false });
    signal?.throwIfAborted();
    if (!page.size) return;
    let last = after;
    for (const [id, item] of page) {
      if (typeof id !== 'string' || !/^\d+$/.test(id) || (after && BigInt(id) <= BigInt(after))) {
        throw new Error('Could not verify all channel viewers');
      }
      if (!last || BigInt(id) > BigInt(last)) last = id;
      yield [id, item];
    }
    if (page.size < limit) return;
    after = last;
  }
}

/** Check the current channel audience, including role and private thread overrides. */
export async function audienceCanRead(interaction, signal) {
  const { guild, channelId, user } = interaction;
  const [channel] = await Promise.all([fetchSource(guild, channelId), guild.roles.fetch()]);
  if (!channel) return false;
  let threadIds;
  if (channel.type === ChannelType.PrivateThread) {
    threadIds = new Set();
    for await (const [id] of fetchPages((options) => channel.members.fetch({ ...options, withMember: true }), 100, signal)) {
      threadIds.add(id);
    }
  }
  let requesterIsVisible = false;
  for await (const [id, member] of fetchPages((options) => guild.members.list(options), 1000, signal)) {
    const permissions = channel.permissionsFor(member);
    if (!permissions) return false;
    if (!permissions.has(Permission.ViewChannel)) continue;
    if (threadIds && !threadIds.has(id) && !permissions.has(Permission.ManageThreads)) continue;
    if (!permissions.has(Permission.ReadMessageHistory)) return false;
    if (id === user.id) requesterIsVisible = true;
  }
  return requesterIsVisible;
}

export async function checkAudience(interaction, canPublish = audienceCanRead) {
  let timeout;
  const controller = new AbortController();
  try {
    return await Promise.race([
      canPublish(interaction, controller.signal),
      new Promise((resolve) => {
        timeout = setTimeout(() => {
          controller.abort();
          resolve(false);
        }, 3000);
      }),
    ]);
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

/** Deliver a result after a private defer. Side-effect notices bypass this function. */
export async function deliverResult(interaction, payload, {
  privateReply = false, sourceChannelId, verifyAccess, canPublish = audienceCanRead, signal,
} = {}) {
  const channel = interaction.channel;
  const publish = !privateReply && channel?.send && (
    sourceChannelId === undefined
    || (sourceChannelId === interaction.channelId && await checkAudience(interaction, canPublish))
  );
  const verified = verifyAccess ? await verifyAccess() : true;
  signal?.throwIfAborted();
  if (!verified) return interaction.editReply('暫時無法確認你仍有來源頻道的讀取權限。');

  if (publish) {
    try {
      await channel.send({ ...payload, allowedMentions: { parse: [] } });
    } catch {
      return interaction.editReply(payload);
    }
    return interaction.deleteReply().catch(() => {});
  }
  return interaction.editReply(payload);
}
