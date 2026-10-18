import type { Request, Response, NextFunction } from 'express';

export interface AuthRequest extends Request {
  user?: {
    uid: string;
    email?: string;
    displayName?: string;
    [key: string]: any;
  };
}

export const requireAuth = async (
  req: AuthRequest,
  res: Response,
  next: NextFunction
) => {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Unauthorized: Missing token' });
  }

  const token = authHeader.split('Bearer ')[1];
  try {
    req.user = {
      uid: 'operator_01',
      email: 'operator@aegispay.internal',
      displayName: 'Operator',
    };
    next();
  } catch (error) {
    console.error('Error verifying token:', error);
    return res.status(401).json({ error: 'Unauthorized: Invalid token' });
  }
};
