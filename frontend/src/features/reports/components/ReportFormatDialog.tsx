import { FileSpreadsheet, FileText, FileType } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/cn";
import type { ReportFormat } from "@/features/reports/utils/reportExports";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  description?: string;
  onSelect: (format: ReportFormat) => void;
  busy?: boolean;
};

const FORMAT_OPTIONS: Array<{
  format: ReportFormat;
  label: string;
  description: string;
  icon: typeof FileText;
}> = [
  {
    format: "pdf",
    label: "PDF",
    description: "Printable document for audits and sharing",
    icon: FileText,
  },
  {
    format: "word",
    label: "Word",
    description: "Editable .docx with tables and metadata",
    icon: FileType,
  },
  {
    format: "excel",
    label: "Excel",
    description: "Spreadsheet .xlsx for analysis and payroll",
    icon: FileSpreadsheet,
  },
];

export function ReportFormatDialog({
  open,
  onOpenChange,
  title = "Choose export format",
  description = "Select how you would like to download this report.",
  onSelect,
  busy = false,
}: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-2">
          {FORMAT_OPTIONS.map((option) => {
            const Icon = option.icon;
            return (
              <Button
                key={option.format}
                type="button"
                variant="secondary"
                disabled={busy}
                className={cn(
                  "h-auto w-full justify-start gap-3 rounded-xl border border-line/80 px-4 py-3 text-left",
                  "hover:border-primary/30 hover:bg-primary-soft/40"
                )}
                onClick={() => {
                  onOpenChange(false);
                  onSelect(option.format);
                }}
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
                  <Icon className="h-5 w-5" strokeWidth={1.75} />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-ink">{option.label}</span>
                  <span className="block text-xs text-ink-muted">{option.description}</span>
                </span>
              </Button>
            );
          })}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
