import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { Prisma } from "@prisma/client";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const configId = searchParams.get("configId");
    const status = searchParams.get("status");

    const where: Prisma.ScanRunWhereInput = {};
    if (configId) where.searchConfigId = Number(configId);
    if (status) where.status = status;

    const runs = await prisma.scanRun.findMany({
      where,
      include: { _count: { select: { priceSnapshots: true } } },
      orderBy: { startedAt: "desc" },
      take: 50,
    });
    return NextResponse.json({ data: runs });
  } catch {
    return NextResponse.json({ error: "Failed to fetch runs" }, { status: 500 });
  }
}
