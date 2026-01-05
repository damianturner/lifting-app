-- schema.sql

CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- BASE TABLES (READ-ONLY FOR USERS)
CREATE TABLE IF NOT EXISTS base_categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS base_exercises (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    default_notes TEXT
);

CREATE TABLE IF NOT EXISTS base_exercise_categories (
    exercise_id INTEGER REFERENCES base_exercises(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES base_categories(id) ON DELETE CASCADE,
    PRIMARY KEY (exercise_id, category_id)
);


-- 1. THE LIBRARIES (USER-SPECIFIC)
CREATE TABLE IF NOT EXISTS Categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    user_id UUID REFERENCES auth.users(id) DEFAULT auth.uid(),
    UNIQUE(name, user_id) -- A user can't have duplicate category names
);

ALTER TABLE Categories ENABLE ROW LEVEL SECURITY;

-- Idempotent Policy Creation
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Categories_Policy') THEN
        CREATE POLICY "Categories_Policy" ON Categories FOR ALL USING (auth.uid() = user_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS ExerciseLibrary (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    default_notes TEXT,
    user_id UUID REFERENCES auth.users(id) DEFAULT auth.uid(),
    UNIQUE(name, user_id)
);

ALTER TABLE ExerciseLibrary ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ExerciseLibrary_Policy') THEN
        CREATE POLICY "ExerciseLibrary_Policy" ON ExerciseLibrary FOR ALL USING (auth.uid() = user_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS ExerciseCategories (
    exercise_id INTEGER REFERENCES ExerciseLibrary(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES Categories(id) ON DELETE CASCADE,
    user_id UUID REFERENCES auth.users(id) DEFAULT auth.uid(),
    PRIMARY KEY (exercise_id, category_id)
);

ALTER TABLE ExerciseCategories ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ExerciseCategories_Policy') THEN
        CREATE POLICY "ExerciseCategories_Policy" ON ExerciseCategories FOR ALL USING (auth.uid() = user_id);
    END IF;
END $$;

-- 2. THE BLUEPRINT
CREATE TABLE IF NOT EXISTS MacroCycles (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    notes TEXT,
    user_id UUID REFERENCES auth.users(id) DEFAULT auth.uid()
);

ALTER TABLE MacroCycles ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'MacroCycles_Policy') THEN
        CREATE POLICY "MacroCycles_Policy" ON MacroCycles FOR ALL USING (auth.uid() = user_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS MiniCycles (
    id SERIAL PRIMARY KEY,
    macro_id INTEGER REFERENCES MacroCycles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    notes TEXT,
    user_id UUID REFERENCES auth.users(id) DEFAULT auth.uid()
);

ALTER TABLE MiniCycles ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'MiniCycles_Policy') THEN
        CREATE POLICY "MiniCycles_Policy" ON MiniCycles FOR ALL USING (auth.uid() = user_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS Workouts (
    id SERIAL PRIMARY KEY,
    mini_id INTEGER REFERENCES MiniCycles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    notes TEXT,
    user_id UUID REFERENCES auth.users(id) DEFAULT auth.uid()
);

ALTER TABLE Workouts ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Workouts_Policy') THEN
        CREATE POLICY "Workouts_Policy" ON Workouts FOR ALL USING (auth.uid() = user_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS PlannedExercises (
    id SERIAL PRIMARY KEY,
    workout_id INTEGER REFERENCES Workouts(id) ON DELETE CASCADE,
    exercise_library_id INTEGER REFERENCES ExerciseLibrary(id) ON DELETE CASCADE,
    sets INTEGER NOT NULL,
    target_rir_json JSONB,
    notes TEXT,
    user_id UUID REFERENCES auth.users(id) DEFAULT auth.uid()
);

ALTER TABLE PlannedExercises ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'PlannedExercises_Policy') THEN
        CREATE POLICY "PlannedExercises_Policy" ON PlannedExercises FOR ALL USING (auth.uid() = user_id);
    END IF;
END $$;

-- 3. THE LOGS
CREATE TABLE IF NOT EXISTS WorkoutLogs (
    id SERIAL PRIMARY KEY,
    workout_id INTEGER REFERENCES Workouts(id) ON DELETE SET NULL,
    completed_at TIMESTAMPTZ DEFAULT NOW(),
    overall_notes TEXT,
    user_id UUID REFERENCES auth.users(id) DEFAULT auth.uid()
);

ALTER TABLE WorkoutLogs ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'WorkoutLogs_Policy') THEN
        CREATE POLICY "WorkoutLogs_Policy" ON WorkoutLogs FOR ALL USING (auth.uid() = user_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS SetLogs (
    id SERIAL PRIMARY KEY,
    workout_log_id INTEGER REFERENCES WorkoutLogs(id) ON DELETE CASCADE,
    planned_exercise_id INTEGER REFERENCES PlannedExercises(id) ON DELETE SET NULL,
    set_number INTEGER NOT NULL,
    weight REAL NOT NULL,
    reps INTEGER NOT NULL,
    rpe INTEGER,
    notes TEXT,
    user_id UUID REFERENCES auth.users(id) DEFAULT auth.uid()
);

ALTER TABLE SetLogs ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'SetLogs_Policy') THEN
        CREATE POLICY "SetLogs_Policy" ON SetLogs FOR ALL USING (auth.uid() = user_id);
    END IF;
END $$;

-- USERS Table
CREATE TABLE IF NOT EXISTS public.users (
  id UUID REFERENCES auth.users(id) NOT NULL PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'PublicUsers_Policy') THEN
        CREATE POLICY "PublicUsers_Policy" ON public.users FOR ALL USING (auth.uid() = id);
    END IF;
END $$;

-- Trigger to update updated_at
DROP TRIGGER IF EXISTS set_public_users_updated_at ON public.users;
CREATE TRIGGER set_public_users_updated_at
BEFORE UPDATE ON public.users
FOR EACH ROW EXECUTE PROCEDURE trigger_set_timestamp();

-- Auth Hook for New Users
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email)
  VALUES (NEW.id, NEW.email)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();