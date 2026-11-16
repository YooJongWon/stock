"use client";

import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

export type Confirmation = {
  title: string;
  description: string;
  confirmLabel: string;
  danger?: boolean;
};

export default function ConfirmDialog({ title, description, confirmLabel, danger, onClose }: Confirmation & {
  onClose: (confirmed: boolean) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = dialogRef.current!;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    dialog.showModal();
    cancelRef.current?.focus();
    document.body.style.overflow = "hidden";
    return () => {
      dialog.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);

  return createPortal(<dialog
    ref={dialogRef}
    className={`confirmation-dialog${danger ? " confirmation-danger" : ""}`}
    aria-labelledby={titleId}
    aria-describedby={descriptionId}
    onCancel={(event) => { event.preventDefault(); onClose(false); }}
    onClick={(event) => {
      if (event.target !== event.currentTarget) return;
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose(false);
    }}
  >
    <div className="confirmation-content">
      <div className="confirmation-heading">
        <div><span>{danger ? "종목 삭제 확인" : "매매 기록 확인"}</span><h2 id={titleId}>{title}</h2></div>
        <button className="portfolio-modal-close" type="button" aria-label="확인창 닫기" onClick={() => onClose(false)}>×</button>
      </div>
      <p id={descriptionId}>{description}</p>
      <div className="confirmation-actions">
        <button ref={cancelRef} type="button" className="confirmation-cancel" onClick={() => onClose(false)}>취소</button>
        <button type="button" className="confirmation-accept" onClick={() => onClose(true)}>{confirmLabel}</button>
      </div>
    </div>
  </dialog>, document.body);
}
