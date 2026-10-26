import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Lesson } from "../../../components/sql/Lesson";
import { isSqlSlug, SQL_SLUGS } from "../../../lib/sql/course";
import { sqlLessonMetadata } from "../../../lib/sql/metadata";

// The eight lessons of /sql, generated at build time; any other slug is a 404.
export const dynamicParams = false;

export function generateStaticParams() {
  return SQL_SLUGS.map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  return isSqlSlug(slug) ? sqlLessonMetadata(slug) : {};
}

export default async function SqlLessonPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!isSqlSlug(slug)) notFound();
  return <Lesson slug={slug} />;
}
