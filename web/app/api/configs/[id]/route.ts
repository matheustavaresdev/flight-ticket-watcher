import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { Prisma } from "@prisma/client";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const numId = Number(id);
    if (Number.isNaN(numId)) {
      return NextResponse.json({ error: "Invalid ID" }, { status: 400 });
    }
    const config = await prisma.searchConfig.findUnique({
      where: { id: numId, active: true },
      include: {
        _count: { select: { scanRuns: true } },
        priceAlerts: { orderBy: { createdAt: "desc" }, take: 1 },
      },
    });
    if (!config) {
      return NextResponse.json({ error: "Config not found" }, { status: 404 });
    }
    return NextResponse.json({ data: config });
  } catch {
    return NextResponse.json({ error: "Failed to fetch config" }, { status: 500 });
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const numId = Number(id);
  if (Number.isNaN(numId)) {
    return NextResponse.json({ error: "Invalid ID" }, { status: 400 });
  }

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {
    const { origin, destination, mustArriveBy, mustStayUntil, maxTripDays } = body;

    if (!origin || !destination || !mustArriveBy || !mustStayUntil || maxTripDays == null) {
      return NextResponse.json(
        { error: "Missing required fields: origin, destination, mustArriveBy, mustStayUntil, maxTripDays" },
        { status: 400 }
      );
    }

    const parsedMaxTripDays = parseInt(String(maxTripDays), 10);
    const parsedMinTripDays = body.minTripDays != null ? parseInt(String(body.minTripDays), 10) : null;

    if (Number.isNaN(parsedMaxTripDays)) {
      return NextResponse.json({ error: "maxTripDays must be a number" }, { status: 400 });
    }
    if (parsedMinTripDays !== null && Number.isNaN(parsedMinTripDays)) {
      return NextResponse.json({ error: "minTripDays must be a number" }, { status: 400 });
    }

    const arriveByDate = new Date(String(mustArriveBy));
    const stayUntilDate = new Date(String(mustStayUntil));

    if (isNaN(arriveByDate.getTime())) {
      return NextResponse.json({ error: "mustArriveBy must be a valid date" }, { status: 400 });
    }
    if (arriveByDate.toISOString().slice(0, 10) !== String(mustArriveBy)) {
      return NextResponse.json({ error: "Invalid mustArriveBy date" }, { status: 400 });
    }
    if (isNaN(stayUntilDate.getTime())) {
      return NextResponse.json({ error: "mustStayUntil must be a valid date" }, { status: 400 });
    }
    if (stayUntilDate.toISOString().slice(0, 10) !== String(mustStayUntil)) {
      return NextResponse.json({ error: "Invalid mustStayUntil date" }, { status: 400 });
    }
    if (stayUntilDate < arriveByDate) {
      return NextResponse.json({ error: "mustStayUntil must be >= mustArriveBy" }, { status: 400 });
    }
    const stayDays = Math.round(
      (stayUntilDate.getTime() - arriveByDate.getTime()) / (1000 * 60 * 60 * 24)
    );
    if (stayDays > parsedMaxTripDays) {
      return NextResponse.json({ error: "Stay window exceeds maxTripDays" }, { status: 400 });
    }
    if (parsedMaxTripDays < 1) {
      return NextResponse.json({ error: "maxTripDays must be >= 1" }, { status: 400 });
    }

    const normalizedOrigin = String(origin).trim().toUpperCase();
    const normalizedDestination = String(destination).trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(normalizedOrigin)) {
      return NextResponse.json({ error: "Invalid origin airport code" }, { status: 400 });
    }
    if (!/^[A-Z]{3}$/.test(normalizedDestination)) {
      return NextResponse.json({ error: "Invalid destination airport code" }, { status: 400 });
    }

    const config = await prisma.searchConfig.update({
      where: { id: numId, active: true },
      data: {
        origin: normalizedOrigin,
        destination: normalizedDestination,
        mustArriveBy: arriveByDate,
        mustStayUntil: stayUntilDate,
        maxTripDays: parsedMaxTripDays,
        minTripDays: parsedMinTripDays,
      },
    });
    return NextResponse.json({ data: config });
  } catch (error) {
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === "P2025") {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json({ error: "Failed to update config" }, { status: 500 });
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const numId = Number(id);
    if (Number.isNaN(numId)) {
      return NextResponse.json({ error: "Invalid ID" }, { status: 400 });
    }
    const updatedRecord = await prisma.searchConfig.update({
      where: { id: numId },
      data: { active: false },
    });
    return NextResponse.json({ data: updatedRecord }, { status: 200 });
  } catch (error) {
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === "P2025") {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json({ error: "Failed to delete config" }, { status: 500 });
  }
}
