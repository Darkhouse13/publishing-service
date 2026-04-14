interface SectionHeadingProps {
  title: string;
}

export default function SectionHeading({ title }: SectionHeadingProps) {
  return (
    <div className="flex items-center gap-4 mb-6">
      <h2 className="text-lg font-black uppercase tracking-widest whitespace-nowrap">
        {title}
      </h2>
      <div className="flex-1 h-[3px] bg-base" />
    </div>
  );
}
