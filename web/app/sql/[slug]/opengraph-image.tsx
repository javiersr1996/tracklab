import { notFound } from "next/navigation";
import { isSqlSlug, SQL_SLUGS } from "../../../lib/sql/course";
import { sqlImage } from "../../../lib/sql/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Pitch & Parquet SQL lesson";

export function generateStaticParams() {
  return SQL_SLUGS.map((slug) => ({ slug }));
}

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!isSqlSlug(slug)) notFound();
  return sqlImage(slug);
}
