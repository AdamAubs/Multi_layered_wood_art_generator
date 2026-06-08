interface ErrorDisplayProps {
  label: string;
  message: string;
}

export function ErrorDisplay({ label, message }: ErrorDisplayProps) {
  return (
    <p className="error-text">
      <strong>{label}:</strong> {message}
    </p>
  );
}
