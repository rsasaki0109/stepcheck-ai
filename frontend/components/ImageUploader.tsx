"use client";

import { useEffect, useState } from "react";

interface Props {
  images: File[];
  onChange: (images: File[]) => void;
}

export default function ImageUploader({ images, onChange }: Props) {
  const [previews, setPreviews] = useState<string[]>([]);

  useEffect(() => {
    const urls = images.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [images]);

  function addFiles(fileList: FileList | null) {
    if (!fileList) return;
    const incoming = Array.from(fileList).filter((f) =>
      f.type.startsWith("image/"),
    );
    onChange([...images, ...incoming]);
  }

  function removeAt(index: number) {
    onChange(images.filter((_, i) => i !== index));
  }

  return (
    <section className="flex h-full flex-col">
      <span className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
        Work images
      </span>

      <label
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          addFiles(e.dataTransfer.files);
        }}
        className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500 transition hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400"
      >
        <span className="font-medium">Drop images here or click to browse</span>
        <span className="mt-1 text-xs">PNG, JPG — one or more</span>
        <input
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
      </label>

      {previews.length > 0 && (
        <div className="mt-4 grid grid-cols-3 gap-3">
          {previews.map((src, i) => (
            <div key={src} className="group relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt={images[i]?.name ?? `image ${i + 1}`}
                className="h-24 w-full rounded-md object-cover ring-1 ring-slate-200 dark:ring-slate-700"
              />
              <button
                type="button"
                onClick={() => removeAt(i)}
                aria-label="Remove image"
                className="absolute right-1 top-1 rounded-full bg-black/60 px-2 text-xs text-white opacity-0 transition group-hover:opacity-100"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
