import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, AlertCircle, Smile, Meh, Frown } from 'lucide-react';
import type { MeetingAnalysis } from '../../types';

interface DisplayTranscriptItem {
  speaker: string;
  text: string;
  start: number;
}

interface MeetingAnalysisPanelProps {
  analysis: MeetingAnalysis | null;
  transcripts: DisplayTranscriptItem[];
}

const emotionColors: Record<string, string> = {
  agreement: 'bg-green-100 text-green-700 border-green-200',
  disagreement: 'bg-red-100 text-red-700 border-red-200',
  hesitation: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  tension: 'bg-orange-100 text-orange-700 border-orange-200'
};

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

export function MeetingAnalysisPanel({ analysis, transcripts }: MeetingAnalysisPanelProps) {
  const safeTranscripts = transcripts || [];

  if (!analysis) {
    return (
      <div className="max-w-7xl mx-auto flex items-center justify-center py-20 text-gray-500">
        <p>Meeting analysis will appear here once the server processes the data.</p>
      </div>
    );
  }

  const { overall_sentiment, engagement_level, engagement_summary, signal_counts, highlights } = analysis;

  const signalChartData = [
    { name: 'Agreement', value: signal_counts.agreement, color: '#10b981' },
    { name: 'Disagreement', value: signal_counts.disagreement, color: '#ef4444' },
    { name: 'Tension', value: signal_counts.tension, color: '#f97316' },
    { name: 'Hesitation', value: signal_counts.hesitation, color: '#eab308' },
  ].filter(item => item.value > 0);

  const emotionalMoments = highlights.map(hl => {
    const transcript = safeTranscripts[hl.transcript_index];
    return {
      time: transcript ? formatTime(transcript.start) : 'Unknown time',
      speaker: transcript ? transcript.speaker : 'Unknown',
      emotion: hl.signal,
      text: transcript ? transcript.text : '',
      type: hl.signal,
      intensity: hl.severity,
      reason: hl.reason
    };
  });

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm text-gray-500">Overall Sentiment</h3>
             {overall_sentiment === 'positive' ? <Smile className="w-5 h-5 text-green-600" /> :
              overall_sentiment === 'negative' ? <Frown className="w-5 h-5 text-red-600" /> :
              <Meh className="w-5 h-5 text-gray-600" />}
          </div>
          <p className="text-gray-900 mb-1 capitalize">{overall_sentiment}</p>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm text-gray-500">Engagement Level</h3>
            <TrendingUp className="w-5 h-5 text-blue-600" />
          </div>
          <p className="text-gray-900 mb-1 capitalize">{engagement_level}</p>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm text-gray-500">Key Moments</h3>
            <AlertCircle className="w-5 h-5 text-orange-600" />
          </div>
          <p className="text-gray-900 mb-1">{highlights.length} Identified</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Signal Counts Distribution */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-gray-900 mb-4">Signal Distribution</h2>
          {signalChartData.length > 0 ? (
             <ResponsiveContainer width="100%" height={250}>
               <PieChart>
                 <Pie
                   data={signalChartData}
                   cx="50%"
                   cy="50%"
                   labelLine={false}
                   label={({ name, value }) => `${name}: ${value}`}
                   outerRadius={80}
                   fill="#8884d8"
                   dataKey="value"
                 >
                   {signalChartData.map((entry, index) => (
                     <Cell key={`cell-${index}`} fill={entry.color} />
                   ))}
                 </Pie>
                 <Tooltip />
               </PieChart>
             </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-500">No signals detected yet.</p>
          )}
        </div>

        {/* Engagement Summary */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-gray-900 mb-4">Engagement Summary</h2>
          <p className="text-sm text-gray-700 leading-relaxed">
            {engagement_summary || 'No summary available.'}
          </p>
        </div>
      </div>

      {/* Emotionally Significant Moments */}
      {emotionalMoments.length > 0 && (
         <div className="bg-white rounded-lg border border-gray-200">
           <div className="px-6 py-4 border-b border-gray-200">
             <h2 className="text-gray-900">Emotionally Significant Moments</h2>
             <p className="text-sm text-gray-500 mt-1">Key emotional dynamics detected during the meeting</p>
           </div>
   
           <div className="divide-y divide-gray-100">
             {emotionalMoments.map((moment, index) => (
               <div key={index} className="p-6">
                 <div className="flex items-start gap-4">
                   <div className={`px-3 py-1 rounded-lg text-sm border capitalize ${emotionColors[moment.type]}`}>
                     {moment.emotion}
                   </div>
   
                   <div className="flex-1">
                     <div className="flex items-center gap-3 mb-2">
                       <span className="text-sm text-gray-900">{moment.speaker}</span>
                       <span className="text-xs text-gray-400">{moment.time}</span>
                       <span className={`text-xs px-2 py-0.5 rounded capitalize ${
                         moment.intensity === 'high' ? 'bg-red-100 text-red-700 border-red-200' : 'bg-yellow-100 text-yellow-700 border-yellow-200'
                       }`}>
                         {moment.intensity} intensity
                       </span>
                     </div>
   
                     <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                       <p className="text-sm text-gray-700 italic">"{moment.text}"</p>
                     </div>
   
                     <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
                        <span className="flex items-center gap-1 text-indigo-600 font-medium">
                          Reason: {moment.reason}
                        </span>
                     </div>
                   </div>
                 </div>
               </div>
             ))}
           </div>
         </div>
      )}
    </div>
  );
}
