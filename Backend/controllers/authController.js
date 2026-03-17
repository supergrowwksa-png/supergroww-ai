const User = require("../models/User");
const Otp = require("../models/Otp");
const sendEmail = require("../utils/sendEmail");
const bcrypt = require("bcryptjs");
const jwt = require("jsonwebtoken");

// =========================
// HELPER: GENERATE JWT
// =========================
const generateToken = (id) => {
  return jwt.sign(
    { id },
    process.env.JWT_SECRET || "your_secret_key",
    { expiresIn: "30d" }
  );
};

// =========================
// SEND OTP
// =========================
exports.sendOtp = async (req, res) => {
  try {
    const { email } = req.body;

    if (!email) {
      return res.status(400).json({ message: "Email is required" });
    }

    const existingUser = await User.findOne({ email });
    if (existingUser) {
      return res.status(400).json({ message: "Email already registered" });
    }

    const otp = Math.floor(100000 + Math.random() * 900000).toString();

    await Otp.findOneAndUpdate(
      { email },
      { otp, createdAt: Date.now() },
      { upsert: true, new: true }
    );

    await sendEmail({
      email,
      subject: "SuperGrow - Email Verification",
      message: `Your OTP is ${otp}. It expires in 5 minutes.`,
    });

    res.status(200).json({
      success: true,
      message: "OTP sent successfully",
    });
  } catch (error) {
    console.error("Send OTP error:", error);
    res.status(500).json({ message: "Failed to send OTP" });
  }
};

// =========================
// SIGNUP
// =========================
exports.signup = async (req, res) => {
  try {
    let {
      title,
      name,
      surname,
      email,
      country,
      phone,
      password,
      otp,
      role, // 🔑 RECEIVE ROLE
    } = req.body;

    if (!name?.trim() || !email || !password || !otp) {
      return res.status(400).json({ message: "Missing required fields" });
    }

    // 🔒 Validate role safely
    if (role && !["recruiter", "candidate"].includes(role)) {
      return res.status(400).json({ message: "Invalid role" });
    }

    const otpRecord = await Otp.findOne({ email });
    if (!otpRecord || otpRecord.otp !== otp) {
      return res.status(400).json({ message: "Invalid or expired OTP" });
    }

    surname = surname?.trim() || "-";

    const user = await User.create({
      title,
      name: name.trim(),
      surname,
      email,
      country,
      phone,
      password, // hashed in model
      role: role || "candidate", // 🔑 STORE ROLE
      profileCompleted: false,
    });

    await Otp.deleteOne({ email });

    res.status(201).json({
      success: true,
      message: "User registered successfully",
      token: generateToken(user._id),
      user: {
        _id: user._id,
        name: user.name,
        email: user.email,
        role: user.role,
        profileCompleted: user.profileCompleted,
      },
    });
  } catch (error) {
    console.error("Signup error:", error);

    if (error.code === 11000) {
      return res
        .status(400)
        .json({ message: "Email already registered" });
    }

    res.status(500).json({ message: "Registration failed" });
  }
};

// =========================
// LOGIN
// =========================
exports.login = async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res
        .status(400)
        .json({ message: "Email and password are required" });
    }

    const user = await User.findOne({ email });
    if (!user) {
      return res
        .status(400)
        .json({ message: "Invalid email or password" });
    }

    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      return res
        .status(400)
        .json({ message: "Invalid email or password" });
    }

    res.status(200).json({
      success: true,
      message: "Login successful",
      token: generateToken(user._id),
      user: {
        _id: user._id,
        name: user.name,
        email: user.email,
        role: user.role,
        profileCompleted: user.profileCompleted,
      },
    });
  } catch (error) {
    console.error("Login error:", error);
    res.status(500).json({ message: "Login failed" });
  }
};

// =========================
// GET LOGGED-IN USER
// =========================
exports.getMe = async (req, res) => {
  try {
    const user = await User.findById(req.user._id).select("-password");

    res.status(200).json({
      success: true,
      user,
    });
  } catch (error) {
    console.error("GetMe error:", error);
    res.status(500).json({ message: "Failed to fetch user" });
  }
};

