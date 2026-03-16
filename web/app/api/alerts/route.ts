import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { Prisma } from "@prisma/client";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const configId = searchParams.get("configId");
    const origin = searchParams.get("origin");
    const destination = searchParams.get("destination");

    const where: Prisma.PriceAlertWhereInput = {};
    if (configId) where.searchConfigId = Number(configId);
    if (origin) where.origin = origin;
    if (destination) where.destination = destination;

    const alerts = await prisma.priceAlert.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: 50,
    });
    return NextResponse.json({ data: alerts });
  } catch {
    return NextResponse.json({ error: "Failed to fetch alerts" }, { status: 500 });
  }
}
