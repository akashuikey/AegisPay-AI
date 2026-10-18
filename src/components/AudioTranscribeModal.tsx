import React, { useState, useRef } from 'react';
import { Mic, MicOff, Loader2, Sparkles, X, Check, Volume2 } from 'lucide-react';

interface AudioTranscribeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onTranscriptionComplete: (text: string) => void;
}

export const AudioTranscribeModal: React.FC<AudioTranscribeModalProps> = ({
  isOpen,
  onClose,
  onTranscriptionComplete,
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcribedText, setTranscribedText] = useState('');
  const [modelUsed, setModelUsed] = useState('gemini-3.5-transcribe');
  const [isSimulated, setIsSimulated] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  if (!isOpen) return null;

  const startRecording = async () => {
    setError(null);
    setTranscribedText('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        // Stop all tracks
        stream.getTracks().forEach((track) => track.stop());
        await processAudio(audioBlob);
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err: any) {
      console.error('Microphone access denied:', err);
      setError('Microphone access denied. You can still test with simulated audio.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const processAudio = async (blob: Blob) => {
    setIsTranscribing(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(blob);
      reader.onloadend = async () => {
        const base64Audio = (reader.result as string).split(',')[1];
        try {
          const res = await fetch('/api/transcribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              audioBase64: base64Audio,
              mimeType: 'audio/webm',
            }),
          });
          const data = await res.json();
          setTranscribedText(data.text || '');
          setModelUsed(data.model || 'gemini-3.5-transcribe');
          setIsSimulated(Boolean(data.is_simulated));
        } catch (fetchErr) {
          // Graceful fallback transcript
          setTranscribedText(
            'The caller claimed I am under digital arrest and warned me not to disconnect or inform anyone.'
          );
          setIsSimulated(true);
        } finally {
          setIsTranscribing(false);
        }
      };
    } catch (err) {
      setError('Failed to process audio recording.');
      setIsTranscribing(false);
    }
  };

  const handleApply = () => {
    if (transcribedText) {
      onTranscriptionComplete(transcribedText);
      onClose();
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.65)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
        padding: 16,
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 480,
          background: '#ffffff',
          borderRadius: 20,
          padding: 24,
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.2)',
          border: '1px solid #e2e8f0',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                background: '#e0f2fe',
                color: '#0284c7',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <Mic size={18} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#0f172a' }}>Audio Transcription</h3>
              <div style={{ fontSize: 11, color: '#64748b', display: 'flex', alignItems: 'center', gap: 4 }}>
                <Sparkles size={11} color="#0284c7" />
                <span>Powered by {modelUsed}</span>
                {isSimulated && (
                  <span style={{ background: '#fef3c7', color: '#b45309', padding: '1px 6px', borderRadius: 4, fontSize: 9, fontWeight: 700 }}>
                    DEMO FALLBACK
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#94a3b8' }}
          >
            <X size={20} />
          </button>
        </div>

        <p style={{ fontSize: 12, color: '#475569', lineHeight: 1.5, margin: '0 0 18px' }}>
          Speak into your microphone to capture customer call testimony. Model <strong>gemini-3.5-transcribe</strong> will transcribe the speech into text to detect coercion and fraud patterns.
        </p>

        {error && (
          <div style={{ padding: '8px 12px', background: '#fee2e2', color: '#b91c1c', borderRadius: 8, fontSize: 11, marginBottom: 14 }}>
            {error}
          </div>
        )}

        {/* Recording Animation / Controls */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px 16px',
            background: isRecording ? '#fff5f5' : '#f8fafc',
            border: isRecording ? '2px dashed #ef4444' : '1px solid #e2e8f0',
            borderRadius: 14,
            marginBottom: 16,
          }}
        >
          {isRecording ? (
            <>
              <button
                type="button"
                onClick={stopRecording}
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: '50%',
                  background: '#ef4444',
                  color: '#ffffff',
                  border: 'none',
                  display: 'grid',
                  placeItems: 'center',
                  boxShadow: '0 0 0 10px rgba(239, 68, 68, 0.2)',
                  cursor: 'pointer',
                  animation: 'pulse-dot 1.2s infinite',
                }}
              >
                <MicOff size={28} />
              </button>
              <div style={{ marginTop: 14, fontWeight: 700, fontSize: 13, color: '#b91c1c' }}>
                Recording... Click to stop
              </div>
              <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                Listening to microphone input
              </div>
            </>
          ) : isTranscribing ? (
            <>
              <Loader2 size={36} color="#0284c7" className="animate-spin" />
              <div style={{ marginTop: 12, fontWeight: 700, fontSize: 13, color: '#0369a1' }}>
                Transcribing audio with gemini-3.5-transcribe...
              </div>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={startRecording}
                style={{
                  width: 60,
                  height: 60,
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #0284c7, #0d9488)',
                  color: '#ffffff',
                  border: 'none',
                  display: 'grid',
                  placeItems: 'center',
                  boxShadow: '0 4px 14px rgba(2, 132, 199, 0.3)',
                  cursor: 'pointer',
                }}
              >
                <Mic size={26} />
              </button>
              <div style={{ marginTop: 12, fontWeight: 700, fontSize: 13, color: '#0f172a' }}>
                Click to Start Recording
              </div>
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                Or test with sample audio transcript below
              </div>
            </>
          )}
        </div>

        {/* Transcribed Text Output */}
        {transcribedText && (
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#334155', display: 'block', marginBottom: 6 }}>
              Transcription Result:
            </label>
            <div
              style={{
                padding: '12px 14px',
                background: '#f8fafc',
                border: '1px solid #cbd5e1',
                borderRadius: 10,
                fontSize: 12,
                color: '#1e293b',
                lineHeight: 1.5,
                maxHeight: 120,
                overflowY: 'auto',
              }}
            >
              "{transcribedText}"
            </div>
          </div>
        )}

        {/* Modal Buttons */}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onClose}
            className="button"
            style={{ padding: '8px 16px', fontSize: 12 }}
          >
            Cancel
          </button>
          {transcribedText ? (
            <button
              type="button"
              onClick={handleApply}
              className="button primary"
              style={{ padding: '8px 18px', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <Check size={14} /> Insert into Dialogue
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                setTranscribedText(
                  'A caller claiming to be Inspector Sharma from the CBI cyber branch told me I am under digital arrest and threatened a non-bailable warrant.'
                );
              }}
              className="button soft"
              style={{ padding: '8px 14px', fontSize: 11 }}
            >
              Use Sample Coercion Audio
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
