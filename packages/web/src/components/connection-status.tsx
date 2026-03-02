import { Wifi, WifiOff } from "lucide-react";
import { useCelery } from "@/hooks/use-celery";

export function ConnectionStatus() {
  const { connected } = useCelery();

  return connected ? (
    <>
      <Wifi className="text-emerald-500" />
      <span>Connected</span>
    </>
  ) : (
    <>
      <WifiOff className="animate-pulse text-muted-foreground" />
      <span>Disconnected</span>
    </>
  );
}
