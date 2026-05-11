import type { ActionItem, MeetingSummary, TranscriptItem } from '../types';

export interface MeetingNotesExportInput {
  summary: MeetingSummary;
  transcripts?: TranscriptItem[];
  meetingDate?: string | null;
  meetingId?: string | null;
  meetingTitle?: string | null;
  template?: MeetingNotesTemplate;
}

export type MeetingNotesTemplate = 'standard' | 'chinese_minutes';

const sanitizeText = (value: string) => value.replace(/\r\n/g, '\n').trim();

const formatDate = (meetingDate?: string | null) => {
  const value = meetingDate ? new Date(meetingDate) : new Date();
  if (Number.isNaN(value.getTime())) {
    return 'Not available';
  }

  return new Intl.DateTimeFormat('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  }).format(value);
};

const formatDuration = (transcripts: TranscriptItem[] = []) => {
  if (!transcripts.length) {
    return 'Not available';
  }

  const start = transcripts[0]?.start ?? 0;
  const end = transcripts.reduce((latest, item) => Math.max(latest, item.end ?? item.start ?? 0), start);
  const totalSeconds = Math.max(0, Math.round(end - start));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes === 0) {
    return `${seconds} seconds`;
  }

  return seconds > 0 ? `${minutes} min ${seconds} sec` : `${minutes} minutes`;
};

const formatTranscriptReference = (item: ActionItem, transcripts: TranscriptItem[]) => {
  if (item.transcript_index == null) {
    return 'Summary';
  }

  const transcript = transcripts[item.transcript_index];
  if (!transcript) {
    return `#${item.transcript_index + 1}`;
  }

  const minutes = Math.floor(transcript.start / 60);
  const seconds = Math.floor(transcript.start % 60);
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

const appendList = (lines: string[], items: string[], emptyText: string) => {
  if (!items.length) {
    lines.push(`- ${emptyText}`);
    return;
  }

  items.forEach((item) => {
    lines.push(`- ${sanitizeText(item)}`);
  });
};

export const buildMeetingNotesMarkdown = ({
  summary,
  transcripts = [],
  meetingDate,
  meetingTitle,
  template = 'standard',
}: MeetingNotesExportInput) => {
  const title = sanitizeText(meetingTitle ?? '') || sanitizeText(summary.title) || 'Meeting Notes';
  const actionItems = summary.action_items.filter((item) => item.is_actionable);
  if (template === 'chinese_minutes') {
    return buildChineseMinutesMarkdown({
      title,
      summary,
      transcripts,
      meetingDate,
      actionItems,
    });
  }
  const lines: string[] = [
    `# ${title}`,
    '',
    `- Date: ${formatDate(meetingDate)}`,
    `- Duration: ${formatDuration(transcripts)}`,
    '',
    '## Overview',
    '',
    sanitizeText(summary.overview) || 'No meeting overview was generated.',
    '',
    '## Key Topics',
    '',
  ];

  appendList(lines, summary.key_topics, 'No key topics extracted.');
  lines.push('', '## Decisions', '');
  appendList(lines, summary.decisions, 'No decisions extracted.');
  lines.push('', '## Risks and Open Questions', '');
  appendList(lines, summary.risks, 'No risks or open questions extracted.');
  lines.push('', '## Follow-up Actions', '');

  if (!actionItems.length) {
    lines.push('- No follow-up actions extracted.');
  } else {
    actionItems.forEach((item) => {
      const details = [
        `Owner: ${sanitizeText(item.assignee) || 'Unassigned'}`,
        `Deadline: ${sanitizeText(item.deadline) || 'Not specified'}`,
        `Status: ${item.status}`,
        `Source: ${formatTranscriptReference(item, transcripts)}`,
        `Confidence: ${Math.round(item.confidence * 100)}%`,
      ];
      lines.push(`- ${sanitizeText(item.task)} (${details.join('; ')})`);
    });
  }

  return `${lines.join('\n')}\n`;
};

const buildChineseMinutesMarkdown = ({
  title,
  summary,
  transcripts,
  meetingDate,
  actionItems,
}: {
  title: string;
  summary: MeetingSummary;
  transcripts: TranscriptItem[];
  meetingDate?: string | null;
  actionItems: ActionItem[];
}) => {
  const lines: string[] = [
    `# ${title}`,
    '',
    `- 会议日期: ${formatDate(meetingDate)}`,
    `- 会议时长: ${formatDuration(transcripts)}`,
    '',
    '## 会议概览',
    '',
    sanitizeText(summary.overview) || '暂无会议概览。',
    '',
    '## 关键议题',
    '',
  ];

  appendList(lines, summary.key_topics, '暂无关键议题。');
  lines.push('', '## 决议', '');
  appendList(lines, summary.decisions, '暂无明确决议。');
  lines.push('', '## 风险与待确认事项', '');
  appendList(lines, summary.risks, '暂无风险或待确认事项。');
  lines.push('', '## 后续行动', '');

  if (!actionItems.length) {
    lines.push('- 暂无后续行动。');
  } else {
    actionItems.forEach((item) => {
      const details = [
        `负责人: ${sanitizeText(item.assignee) || '未分配'}`,
        `截止时间: ${sanitizeText(item.deadline) || '未指定'}`,
        `状态: ${item.status}`,
        `来源: ${formatTranscriptReference(item, transcripts)}`,
        `置信度: ${Math.round(item.confidence * 100)}%`,
      ];
      lines.push(`- ${sanitizeText(item.task)} (${details.join('; ')})`);
    });
  }

  return `${lines.join('\n')}\n`;
};

export const buildActionItemsMarkdown = ({
  summary,
  transcripts = [],
  meetingDate,
  meetingTitle,
}: MeetingNotesExportInput) => {
  const title = sanitizeText(meetingTitle ?? '') || sanitizeText(summary.title) || 'Meeting Action Items';
  const actionItems = summary.action_items.filter((item) => item.is_actionable);
  const lines = [
    `# ${title} - Action Items`,
    '',
    `- Date: ${formatDate(meetingDate)}`,
    '',
    '| Task | Owner | Deadline | Status | Source | Confidence |',
    '| --- | --- | --- | --- | --- | --- |',
  ];

  if (!actionItems.length) {
    lines.push('| No follow-up actions extracted. |  |  |  |  |  |');
  } else {
    actionItems.forEach((item) => {
      lines.push(
        `| ${escapeTableCell(item.task)} | ${escapeTableCell(item.assignee || 'Unassigned')} | ${escapeTableCell(item.deadline || 'Not specified')} | ${item.status} | ${formatTranscriptReference(item, transcripts)} | ${Math.round(item.confidence * 100)}% |`
      );
    });
  }

  return `${lines.join('\n')}\n`;
};

const escapeTableCell = (value: string) => sanitizeText(value).replace(/\|/g, '\\|').replace(/\n/g, ' ');

export const buildMeetingNotesFilename = (
  summary: MeetingSummary,
  meetingId?: string | null,
  meetingTitle?: string | null,
  suffix = ''
) => {
  const baseName = sanitizeText(meetingTitle ?? '') || sanitizeText(summary.title) || meetingId || 'meeting-notes';
  const safeName = baseName
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .toLowerCase();

  const normalizedSuffix = suffix
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .toLowerCase();
  return `${safeName || 'meeting-notes'}${normalizedSuffix ? `-${normalizedSuffix}` : ''}.md`;
};

export const downloadMeetingNotesMarkdown = (input: MeetingNotesExportInput) => {
  const markdown = buildMeetingNotesMarkdown(input);
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = buildMeetingNotesFilename(input.summary, input.meetingId, input.meetingTitle);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
};

export const downloadActionItemsMarkdown = (input: MeetingNotesExportInput) => {
  const markdown = buildActionItemsMarkdown(input);
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = buildMeetingNotesFilename(input.summary, input.meetingId, input.meetingTitle, 'action-items');
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
};
